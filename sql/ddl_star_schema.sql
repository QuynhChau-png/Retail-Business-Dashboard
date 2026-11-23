-- ============================================================
-- DDL - Star Schema cho Data Warehouse Bán Lẻ
-- Tương thích: SQL Server / PostgreSQL (kiểu dữ liệu có thể cần
-- điều chỉnh đôi chút tuỳ hệ quản trị, vd DATE thay vì DATETIME2)
-- ============================================================

USE RetailDW;
GO

-- Xoá bảng cũ nếu tồn tại (thứ tự: Fact trước, Dim sau)
DROP TABLE IF EXISTS FactReturns;
DROP TABLE IF EXISTS FactSales;
DROP TABLE IF EXISTS DimProduct;
DROP TABLE IF EXISTS DimCustomer;
DROP TABLE IF EXISTS DimDate;
DROP TABLE IF EXISTS DimCountry;
GO

-- ------------------------------------------------------------
-- DIMENSION: Sản phẩm
-- ------------------------------------------------------------
CREATE TABLE DimProduct (
    ProductID   INT PRIMARY KEY,
    StockCode   VARCHAR(20)  NOT NULL,
    Description VARCHAR(255) NOT NULL
);
GO

-- ------------------------------------------------------------
-- DIMENSION: Khách hàng
-- CustomerKey = -1 đại diện cho "Unknown Customer" (giao dịch
-- không xác định được khách hàng, nhưng doanh thu vẫn thật)
-- ------------------------------------------------------------
CREATE TABLE DimCustomer (
    CustomerKey   INT PRIMARY KEY, -- giữ nguyên để gán -1 cho Unknown
    CustomerLabel VARCHAR(50)  NOT NULL,
    Country       VARCHAR(100) NOT NULL
);
GO

-- ------------------------------------------------------------
-- DIMENSION: Thời gian
-- DateID dạng YYYYMMDD (INT) để join nhanh và dễ lọc trong DAX
-- ------------------------------------------------------------
CREATE TABLE DimDate (
    DateID    INT PRIMARY KEY, -- YYYYMMDD
    FullDate  DATE NOT NULL,
    Year      INT NOT NULL,
    Quarter   INT NOT NULL,
    Month     INT NOT NULL,
    MonthName VARCHAR(20) NOT NULL,
    Day       INT NOT NULL,
    Weekday   VARCHAR(20) NOT NULL
);
GO

-- ------------------------------------------------------------
-- DIMENSION: Quốc gia / Khu vực
-- ------------------------------------------------------------
CREATE TABLE DimCountry (
    CountryID INT PRIMARY KEY,
    Country   VARCHAR(100) NOT NULL
);
GO

-- ------------------------------------------------------------
-- FACT: Giao dịch bán hàng (chỉ đơn bán hợp lệ)
-- Mỗi dòng = 1 dòng chi tiết hoá đơn (line item)
-- Đơn hủy/trả hàng (InvoiceNo bắt đầu "C" hoặc Quantity < 0) nằm ở FactReturns
-- ------------------------------------------------------------
CREATE TABLE FactSales (
    SalesID      INT PRIMARY KEY,
    InvoiceNo    VARCHAR(20) NOT NULL,
    ProductID    INT NOT NULL,
    CustomerKey  INT NOT NULL,
    DateID       INT NOT NULL,
    CountryID    INT NOT NULL,
	InvoiceDateTime DATETIME2 NOT NULL,
    Quantity     INT NOT NULL,
    UnitPrice    DECIMAL(10,2) NOT NULL,
    Revenue      DECIMAL(14,2) NOT NULL,

    CONSTRAINT FK_Fact_Product  FOREIGN KEY (ProductID)   REFERENCES DimProduct(ProductID),
    CONSTRAINT FK_Fact_Customer FOREIGN KEY (CustomerKey) REFERENCES DimCustomer(CustomerKey),
    CONSTRAINT FK_Fact_Date     FOREIGN KEY (DateID)      REFERENCES DimDate(DateID),
    CONSTRAINT FK_Fact_Country  FOREIGN KEY (CountryID)   REFERENCES DimCountry(CountryID)
);
GO

-- ------------------------------------------------------------
-- FACT: Đơn trả hàng / hủy riêng biệt
-- ------------------------------------------------------------
CREATE TABLE FactReturns (
    ReturnID		INT  PRIMARY KEY,
    InvoiceNo		VARCHAR(20) NOT NULL,
    ProductID		INT NOT NULL,
    CustomerKey		INT NOT NULL,
    DateID			INT NOT NULL,
    CountryID		INT NOT NULL,
	InvoiceDateTime DATETIME2 NOT NULL,
    ReturnQuantity  INT NOT NULL,
    UnitPrice		DECIMAL(10,2) NOT NULL,
    ReturnValue		DECIMAL(12,2) NOT NULL,

    CONSTRAINT FK_Return_Product  FOREIGN KEY (ProductID)   REFERENCES DimProduct(ProductID),
    CONSTRAINT FK_Return_Customer FOREIGN KEY (CustomerKey) REFERENCES DimCustomer(CustomerKey),
    CONSTRAINT FK_Return_Date     FOREIGN KEY (DateID)      REFERENCES DimDate(DateID),
    CONSTRAINT FK_Return_Country  FOREIGN KEY (CountryID)   REFERENCES DimCountry(CountryID)
);
GO

-- ============================================================
-- INDEX: FactSales
-- ============================================================

-- Phân tích sản phẩm theo thời gian
CREATE INDEX IX_FactSales_Date_Product
ON FactSales(DateID, ProductID);

-- Phân tích hành vi khách hàng theo thời gian
CREATE INDEX IX_FactSales_Customer_Date
ON FactSales(CustomerKey, DateID);

-- Phân tích theo quốc gia
CREATE INDEX IX_FactSales_CountryID
ON FactSales(CountryID);

-- Tra cứu hóa đơn
CREATE INDEX IX_FactSales_InvoiceNo
ON FactSales(InvoiceNo);
GO

-- ============================================================
-- INDEX: FactReturns
-- ============================================================

CREATE INDEX IX_FactReturns_Date_Product
ON FactReturns(DateID, ProductID);

CREATE INDEX IX_FactReturns_Customer_Date
ON FactReturns(CustomerKey, DateID);

CREATE INDEX IX_FactReturns_CountryID
ON FactReturns(CountryID);

CREATE INDEX IX_FactReturns_InvoiceNo
ON FactReturns(InvoiceNo);
GO

--test
SELECT COUNT(*) AS SalesRows FROM FactSales;
SELECT COUNT(*) AS ReturnRows FROM FactReturns;

SELECT SUM(Revenue) AS GrossRevenue
FROM FactSales;

SELECT SUM(ReturnValue) AS ReturnValue
FROM FactReturns;