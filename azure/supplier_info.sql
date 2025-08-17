IF OBJECT_ID('dbo.SupplierInfo') IS NOT NULL DROP TABLE dbo.SupplierInfo;
CREATE TABLE dbo.SupplierInfo (
    SupplierName NVARCHAR(200),
    HeadquartersCountry NVARCHAR(100),
    ProductionCountry NVARCHAR(100),
    Region NVARCHAR(100)
);