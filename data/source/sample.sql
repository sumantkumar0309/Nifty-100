CREATE TABLE `companies` (
  `company_id` varchar(20),
  `company_name` varchar(255),
  `website` varchar(255),
  `face_value` decimal(10,2),
  `book_value` decimal(10,2)
);
CREATE TABLE `analysis` (
  `company_id` varchar(20),
  `growth` varchar(50),
  `roe` varchar(50)
);
CREATE TABLE `balancesheet` (
  `company_id` varchar(20),
  `year` varchar(20),
  `equity_capital` decimal(12,2),
  `reserves` decimal(12,2),
  `borrowings` decimal(12,2),
  `total_assets` decimal(12,2)
);
CREATE TABLE `profitandloss` (
  `company_id` varchar(20),
  `year` varchar(20),
  `sales` decimal(12,2),
  `expenses` decimal(12,2),
  `operating_profit` decimal(12,2),
  `interest` decimal(12,2),
  `net_profit` decimal(12,2)
);
CREATE TABLE `cashflow` (
  `company_id` varchar(20),
  `year` varchar(20),
  `operating_activity` decimal(12,2),
  `investing_activity` decimal(12,2),
  `financing_activity` decimal(12,2),
  `net_cash_flow` decimal(12,2)
);
CREATE TABLE `prosandcons` (
  `company_id` varchar(20),
  `pros` text,
  `cons` text
);
CREATE TABLE `documents` (
  `company_id` varchar(20),
  `year` varchar(20),
  `report_link` text
);
INSERT INTO `companies` VALUES ('TCS','Tata Consultancy Services','https://www.tcs.com',1.00,250.00),('INFY','Infosys Ltd','https://www.infosys.com',5.00,180.00);
INSERT INTO `analysis` VALUES ('TCS','10 Years: 14.2%','10 Years: 24.1%'),('INFY','5 Years: 12.0%','5 Years: 22.3%');
INSERT INTO `balancesheet` VALUES ('TCS','Mar-24',375.00,95000.00,1200.00,140000.00),('INFY','Mar 2024',420.00,74000.00,800.00,110000.00);
INSERT INTO `profitandloss` VALUES ('TCS','Mar-24',245000.00,182000.00,63000.00,1500.00,46000.00),('INFY','Mar 2024',153000.00,112000.00,41000.00,900.00,30000.00);
INSERT INTO `cashflow` VALUES ('TCS','Mar-24',51000.00,-14000.00,-8000.00,29000.00),('INFY','Mar 2024',36000.00,-10000.00,-6000.00,20000.00);
INSERT INTO `prosandcons` VALUES ('TCS','Strong cash generation; High ROE','Valuation expensive'),('INFY','Global delivery strength','Margin pressure');
INSERT INTO `documents` VALUES ('TCS','Mar 2024','https://example.com/tcs-2024.pdf'),('INFY','Mar 2024','https://example.com/infy-2024.pdf');
