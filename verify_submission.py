#!/usr/bin/env python3
"""
Project Submission Verification Script
Checks that all required files and components are in place.
"""

import os
import json
from pathlib import Path

def check_file_exists(path, description):
    """Check if a file exists and print status."""
    exists = os.path.isfile(path)
    status = "✅" if exists else "❌"
    print(f"{status} {description}")
    return exists

def check_directory_exists(path, description):
    """Check if a directory exists and print status."""
    exists = os.path.isdir(path)
    status = "✅" if exists else "❌"
    print(f"{status} {description}")
    return exists

def check_file_contains(path, keywords, description):
    """Check if a file contains specific keywords."""
    if not os.path.isfile(path):
        print(f"❌ {description} (file not found)")
        return False
    
    try:
        with open(path, 'r') as f:
            content = f.read().lower()
            found = all(kw.lower() in content for kw in keywords)
            status = "✅" if found else "❌"
            print(f"{status} {description}")
            return found
    except Exception as e:
        print(f"❌ {description} (error: {e})")
        return False

def main():
    print("\n" + "="*60)
    print("NIFTY 100 PROJECT SUBMISSION VERIFICATION")
    print("="*60 + "\n")
    
    passed = 0
    total = 0
    
    # Check root files
    print("📄 Documentation Files:")
    files_to_check = [
        ("README.md", "README with project overview"),
        (".env.example", ".env.example with configuration template"),
        ("requirements.txt", "requirements.txt with dependencies"),
        ("Dockerfile", "Dockerfile for production image"),
        ("docker-compose.prod.yml", "Docker Compose production stack"),
        ("ARCHITECTURE.md", "Architecture & design document"),
        ("DEPLOYMENT.md", "Production deployment guide"),
        ("BACKEND2_IMPORT_SUMMARY.md", "Backend 2 features summary"),
        ("SUBMISSION_CHECKLIST.md", "Submission checklist"),
    ]
    
    for file, desc in files_to_check:
        if check_file_exists(file, desc):
            passed += 1
        total += 1
    
    # Check directories
    print("\n📁 Core Directories:")
    dirs_to_check = [
        ("orchestration/backend2", "Backend 2 orchestration"),
        ("etl", "ETL pipeline"),
        ("django_app", "Django application"),
        ("analytics", "Analytics engine"),
        ("notebooks", "Jupyter notebooks"),
        ("data/clean", "Clean data directory"),
        ("data/raw", "Raw data directory"),
        ("data/source", "Source data directory"),
        ("docker", "Docker configuration"),
        ("docs", "Documentation"),
    ]
    
    for dir_path, desc in dirs_to_check:
        if check_directory_exists(dir_path, desc):
            passed += 1
        total += 1
    
    # Check Backend 2 modules
    print("\n🔧 Backend 2 Modules:")
    backend2_modules = [
        ("orchestration/backend2/__init__.py", "Backend 2 package init"),
        ("orchestration/backend2/celery_app.py", "Celery app configuration"),
        ("orchestration/backend2/tasks.py", "Background task definitions"),
        ("orchestration/backend2/cache.py", "Redis caching layer"),
        ("orchestration/backend2/partner_auth.py", "Partner API authentication"),
        ("orchestration/backend2/webhook.py", "Webhook delivery"),
        ("orchestration/backend2/config.py", "Configuration loader"),
        ("orchestration/backend2/logging_utils.py", "Structured logging"),
        ("orchestration/backend2/module_runner.py", "ETL executor"),
    ]
    
    for file_path, desc in backend2_modules:
        if check_file_exists(file_path, desc):
            passed += 1
        total += 1
    
    # Check analytics modules
    print("\n📊 Analytics Modules:")
    analytics_modules = [
        ("etl/proscons_generator.py", "Pros/cons generation"),
        ("etl/anomaly_detector.py", "Anomaly detection"),
        ("etl/trend_analyzer.py", "Trend analysis & forecasting"),
    ]
    
    for file_path, desc in analytics_modules:
        if check_file_exists(file_path, desc):
            passed += 1
        total += 1
    
    # Check Docker configuration
    print("\n🐳 Docker Configuration:")
    docker_files = [
        ("docker/nginx/conf.d/default.conf", "Nginx reverse proxy config"),
        (".dockerignore", "Docker ignore file"),
    ]
    
    for file_path, desc in docker_files:
        if check_file_exists(file_path, desc):
            passed += 1
        total += 1
    
    # Check GitHub Actions
    print("\n🚀 CI/CD Pipeline:")
    if check_file_exists(".github/workflows/ci-pipeline.yml", "GitHub Actions CI/CD"):
        passed += 1
    total += 1
    
    # Check requirements.txt for key packages
    print("\n📦 Dependencies Check:")
    required_packages = [
        ("requirements.txt", ["celery", "redis", "django", "djangorestframework", 
                             "sqlalchemy", "pandas", "scikit-learn"], "Key dependencies"),
    ]
    
    for file_path, packages, desc in required_packages:
        if check_file_contains(file_path, packages, desc):
            passed += 1
        total += 1
    
    # Check Django app structure
    print("\n📱 Django App Structure:")
    django_files = [
        ("django_app/manage.py", "Django manage.py"),
        ("django_app/config/settings.py", "Django settings"),
        ("django_app/config/urls.py", "Django URL configuration"),
        ("django_app/apps/partner_api", "Partner API app"),
        ("django_app/apps/public", "Public app"),
        ("django_app/apps/warehouse", "Warehouse app"),
    ]
    
    for file_path, desc in django_files:
        if check_directory_exists(file_path, desc) if file_path.endswith("/") else check_file_exists(file_path, desc):
            passed += 1
        total += 1
    
    # Summary
    print("\n" + "="*60)
    percentage = (passed / total * 100) if total > 0 else 0
    print(f"✅ VERIFICATION COMPLETE: {passed}/{total} checks passed ({percentage:.1f}%)")
    print("="*60 + "\n")
    
    if percentage == 100:
        print("🎉 Project is ready for submission!")
        print("\n📝 Next steps before deployment:")
        print("  1. Configure .env file with actual passwords")
        print("  2. Create SQL dump at data/source/scriptticker.sql")
        print("  3. Generate SSL certificates in docker/ssl/")
        print("  4. Configure GitHub Actions secrets")
        print("  5. Run: docker-compose -f docker-compose.prod.yml up -d")
        print("  6. Verify all services are healthy: docker-compose ps")
        return 0
    else:
        print("⚠️  Some items are missing. Please review the checklist above.")
        return 1

if __name__ == "__main__":
    exit(main())
