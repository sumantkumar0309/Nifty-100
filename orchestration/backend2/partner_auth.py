"""Channel Partner API Authentication - Token-based auth with rate limiting"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend2.logging_utils import get_logger

logger = get_logger(__name__)


def get_database_session():
    """Get SQLAlchemy session for database operations"""
    import os
    
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/nifty100_warehouse"
    )
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    return Session()


def generate_api_token(partner_id: str, partner_name: str) -> dict[str, Any]:
    """
    Generate a new API token for a channel partner.
    
    Args:
        partner_id: Unique identifier for the partner
        partner_name: Name of the partner organization
    
    Returns:
        Dictionary with token, secret, and metadata
    """
    try:
        # Generate token: 32-byte random hex string
        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Generate secret: 32-byte random hex string
        secret = secrets.token_hex(32)
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()
        
        session = get_database_session()
        
        # Store token in database
        insert_query = text("""
            INSERT INTO partner_api_tokens 
            (partner_id, partner_name, token_hash, secret_hash, created_at, expires_at, is_active)
            VALUES 
            (:partner_id, :partner_name, :token_hash, :secret_hash, :created_at, :expires_at, :is_active)
        """)
        
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=365)  # 1-year validity
        
        session.execute(insert_query, {
            'partner_id': partner_id,
            'partner_name': partner_name,
            'token_hash': token_hash,
            'secret_hash': secret_hash,
            'created_at': now,
            'expires_at': expires_at,
            'is_active': True
        })
        session.commit()
        session.close()
        
        logger.info(
            f"Generated API token for partner {partner_id}",
            extra={"event": "api_token_generated", "extra_data": {"partner_id": partner_id}}
        )
        
        return {
            "token": token,
            "secret": secret,
            "partner_id": partner_id,
            "partner_name": partner_name,
            "expires_at": expires_at.isoformat(),
            "note": "Keep secret safe. This secret will not be shown again."
        }
        
    except Exception as e:
        logger.error(f"Error generating API token: {str(e)}")
        raise


def validate_api_token(token: str, secret: str) -> tuple[bool, Optional[str], Optional[dict[str, Any]]]:
    """
    Validate API token and secret.
    
    Args:
        token: API token
        secret: API secret
    
    Returns:
        Tuple of (is_valid, error_message, partner_info)
    """
    try:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()
        
        session = get_database_session()
        
        query = text("""
            SELECT partner_id, partner_name, is_active, expires_at
            FROM partner_api_tokens
            WHERE token_hash = :token_hash AND secret_hash = :secret_hash
        """)
        
        result = session.execute(
            query, {'token_hash': token_hash, 'secret_hash': secret_hash}
        ).fetchone()
        session.close()
        
        if not result:
            return False, "Invalid token or secret", None
        
        partner_id, partner_name, is_active, expires_at = result
        
        if not is_active:
            return False, "Token is inactive", None
        
        if expires_at < datetime.now(timezone.utc):
            return False, "Token has expired", None
        
        partner_info = {
            "partner_id": partner_id,
            "partner_name": partner_name,
        }
        
        return True, None, partner_info
        
    except Exception as e:
        logger.error(f"Error validating API token: {str(e)}")
        return False, f"Validation error: {str(e)}", None


def log_api_usage(
    partner_id: str,
    endpoint: str,
    method: str,
    response_status: int,
    response_time_ms: float,
    request_size_bytes: int = 0,
    response_size_bytes: int = 0,
) -> None:
    """
    Log API usage for rate limiting and analytics.
    
    Args:
        partner_id: Partner identifier
        endpoint: API endpoint path
        method: HTTP method (GET, POST, etc.)
        response_status: HTTP response status code
        response_time_ms: Response time in milliseconds
        request_size_bytes: Request payload size
        response_size_bytes: Response payload size
    """
    try:
        session = get_database_session()
        
        insert_query = text("""
            INSERT INTO api_usage_log 
            (partner_id, endpoint, method, response_status, response_time_ms, 
             request_size_bytes, response_size_bytes, timestamp)
            VALUES 
            (:partner_id, :endpoint, :method, :response_status, :response_time_ms, 
             :request_size_bytes, :response_size_bytes, :timestamp)
        """)
        
        session.execute(insert_query, {
            'partner_id': partner_id,
            'endpoint': endpoint,
            'method': method,
            'response_status': response_status,
            'response_time_ms': response_time_ms,
            'request_size_bytes': request_size_bytes,
            'response_size_bytes': response_size_bytes,
            'timestamp': datetime.now(timezone.utc)
        })
        session.commit()
        session.close()
        
    except Exception as e:
        logger.warning(f"Error logging API usage: {str(e)}")


def check_rate_limit(partner_id: str, requests_per_minute: int = 60) -> tuple[bool, dict[str, Any]]:
    """
    Check if partner has exceeded rate limit (requests per minute).
    
    Args:
        partner_id: Partner identifier
        requests_per_minute: Maximum allowed requests per minute
    
    Returns:
        Tuple of (is_allowed, rate_limit_info)
    """
    try:
        session = get_database_session()
        
        one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
        
        count_query = text("""
            SELECT COUNT(*) as request_count
            FROM api_usage_log
            WHERE partner_id = :partner_id AND timestamp > :one_minute_ago
        """)
        
        result = session.execute(count_query, {
            'partner_id': partner_id,
            'one_minute_ago': one_minute_ago
        }).fetchone()
        
        request_count = result[0] if result else 0
        session.close()
        
        is_allowed = request_count < requests_per_minute
        remaining = max(0, requests_per_minute - request_count)
        
        rate_limit_info = {
            "limit": requests_per_minute,
            "used": request_count,
            "remaining": remaining,
            "reset_in_seconds": 60
        }
        
        return is_allowed, rate_limit_info
        
    except Exception as e:
        logger.warning(f"Error checking rate limit: {str(e)}")
        return True, {"note": "Rate limit check failed, allowing request"}


def get_partner_usage_stats(partner_id: str, days: int = 30) -> dict[str, Any]:
    """
    Get API usage statistics for a partner over the specified period.
    
    Args:
        partner_id: Partner identifier
        days: Number of days to look back (default: 30)
    
    Returns:
        Dictionary with usage statistics
    """
    try:
        session = get_database_session()
        
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        stats_query = text("""
            SELECT 
                COUNT(*) as total_requests,
                COUNT(DISTINCT DATE(timestamp)) as days_active,
                AVG(response_time_ms) as avg_response_time_ms,
                MAX(response_time_ms) as max_response_time_ms,
                SUM(response_size_bytes) as total_response_bytes,
                COUNT(CASE WHEN response_status >= 400 THEN 1 END) as error_requests,
                COUNT(CASE WHEN response_status = 200 THEN 1 END) as success_requests
            FROM api_usage_log
            WHERE partner_id = :partner_id AND timestamp > :since_date
        """)
        
        result = session.execute(stats_query, {
            'partner_id': partner_id,
            'since_date': since_date
        }).fetchone()
        
        session.close()
        
        if result:
            total_requests, days_active, avg_response_time, max_response_time, total_bytes, errors, successes = result
            
            return {
                "period_days": days,
                "total_requests": total_requests or 0,
                "days_active": days_active or 0,
                "avg_response_time_ms": float(avg_response_time or 0),
                "max_response_time_ms": float(max_response_time or 0),
                "total_response_bytes": total_bytes or 0,
                "error_count": errors or 0,
                "success_count": successes or 0,
                "success_rate": f"{((successes or 0) / (total_requests or 1) * 100):.1f}%"
            }
        
        return {"error": "No data found"}
        
    except Exception as e:
        logger.error(f"Error retrieving usage stats: {str(e)}")
        return {"error": str(e)}
