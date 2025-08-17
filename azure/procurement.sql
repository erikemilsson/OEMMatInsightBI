IF OBJECT_ID('dbo.Procurement') IS NOT NULL DROP TABLE dbo.Procurement;
CREATE TABLE dbo.Procurement (
    [Date] DATE,
    MaterialName NVARCHAR(100),
    SupplierName NVARCHAR(200),
    Region NVARCHAR(100),
    Quantity DECIMAL(18,2),
    Unit NVARCHAR(50),
    UnitPriceEUR DECIMAL(18,2)
);