"""
ETL - Online Retail Dataset -> Star Schema
=====================================================
Mục đích: Đọc dữ liệu bán lẻ thô từ CSV, làm sạch, chuẩn hóa và biến đổi
thành mô hình Star Schema (2 bảng Fact + 4 bảng Dimension) để nạp vào
Data Warehouse, phục vụ phân tích trên Power BI.

Luồng xử lý:
  1. EXTRACT : Đọc file CSV thô
  2. TRANSFORM: Làm sạch dữ liệu (5 bước) + xây dựng các bảng Dim/Fact
  3. LOAD    : Ghi ra CSV (để import Power BI) + nạp vào SQL Server thật
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import os
from urllib.parse import quote_plus

# ============================================================
# CẤU HÌNH ĐƯỜNG DẪN (tự động xác định theo vị trí file, không phụ)
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Nếu file này nằm trong scripts/, lùi 1 cấp để về thư mục gốc project
if os.path.basename(BASE_DIR).lower() == "scripts":
    BASE_DIR = os.path.dirname(BASE_DIR)

INPUT_FILE = os.path.join(BASE_DIR, "data", "online_retail.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# ============================================================
# CẤU HÌNH KẾT NỐI SQL SERVER
# Windows Authentication -> không cần user/password
# Tên server đọc từ biến môi trường SQL_SERVER_NAME (mặc định: localhost)
# ============================================================
SQL_SERVER_NAME = os.getenv("SQL_SERVER_NAME", "localhost")
SQL_DATABASE_NAME = os.getenv("SQL_DATABASE_NAME", "RetailDW")

_ODBC = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={SQL_SERVER_NAME};"
    f"DATABASE={SQL_DATABASE_NAME};"
    "Trusted_Connection=yes;Encrypt=no;TrustServerCertificate=yes;"
)
CONNECTION_STRING = f"mssql+pyodbc:///?odbc_connect={quote_plus(_ODBC)}"

# Các StockCode không phải sản phẩm thật (phí, điều chỉnh, từ thiện...)
NON_PRODUCT_CODES = ["POST", "DOT", "M", "D", "BANK CHARGES", "CRUK", "PADS", "C2", "AMAZONFEE"]

os.makedirs(OUTPUT_DIR, exist_ok=True)


def extract(path: str) -> pd.DataFrame:
    """Bước 1: Đọc dữ liệu thô."""
    df = pd.read_csv(path, encoding="latin1")
    print(f"[EXTRACT] Đã đọc {len(df):,} dòng từ {path}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bước 2: Làm sạch và biến đổi dữ liệu theo các quy tắc đã xác định.
    Trả về DataFrame đã xử lý, sẵn sàng để xây dựng các bảng Fact/Dimension.
    """
    df = df.copy()
    n_start = len(df)

    # (1) Chuẩn hóa kiểu dữ liệu
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], format="mixed",dayfirst=True)
    df["StockCode"] = df["StockCode"].astype(str).str.strip().str.upper()
    df["InvoiceNo"] = df["InvoiceNo"].astype(str).str.strip()

    # (2) Đánh dấu đơn hủy (InvoiceNo bắt đầu bằng 'C') và Quantity âm
    df["IsCancelled"] = (df["InvoiceNo"].str.startswith("C") | (df["Quantity"] < 0)).astype(int)

    # (3) Loại bỏ dòng phi sản phẩm (phí bưu điện, điều chỉnh, từ thiện...)
    mask_non_product = df["StockCode"].isin(NON_PRODUCT_CODES)
    n_removed_nonproduct = mask_non_product.sum()
    df = df[~mask_non_product]

    # (4) Loại bỏ UnitPrice <= 0 (không phải giao dịch bán hàng thật)
    n_removed_price = (df["UnitPrice"] <= 0).sum()
    df = df[df["UnitPrice"] > 0]

    # (5) Xử lý CustomerID null -> gán "Unknown" thay vì xóa (giữ doanh thu thật)
    df["CustomerID"] = df["CustomerID"].fillna(-1).astype(int)

    # (6) Xử lý Description null -> "Unknown Product"
    df["Description"] = df["Description"].fillna("UNKNOWN PRODUCT").str.strip()

    # (7) Tính cột Revenue
    df["Revenue"] = df["Quantity"] * df["UnitPrice"]    

    print(f"[TRANSFORM-CLEAN] Loại {n_removed_nonproduct:,} dòng phi sản phẩm, "
          f"{n_removed_price:,} dòng UnitPrice<=0")
    print(f"[TRANSFORM-CLEAN] Còn lại {len(df):,}/{n_start:,} dòng "
          f"({len(df)/n_start:.1%})")
    return df


def build_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    """Phải tạo đủ MỌI ngày liên tục (kể cả ngày không có giao dịch),
    không chỉ lấy ngày xuất hiện trong dữ liệu. Đây là yêu cầu bắt buộc của
    DAX Time Intelligence (DATEADD, SAMEPERIODLASTYEAR...) - nếu DimDate bị
    thiếu ngày (không liên tục), các hàm so sánh kỳ trước sẽ tính sai hoặc lỗi."""
    start_date = df["InvoiceDate"].min().normalize()
    end_date = df["InvoiceDate"].max().normalize()
    dates = pd.DataFrame({"FullDate": pd.date_range(start=start_date, end=end_date, freq="D")})
 
    dates["DateID"] = dates["FullDate"].dt.strftime("%Y%m%d").astype(int)
    dates["Year"] = dates["FullDate"].dt.year
    dates["Quarter"] = dates["FullDate"].dt.quarter
    dates["Month"] = dates["FullDate"].dt.month
    dates["MonthName"] = dates["FullDate"].dt.strftime("%B")
    dates["Day"] = dates["FullDate"].dt.day
    dates["Weekday"] = dates["FullDate"].dt.day_name()
    return dates[["DateID", "FullDate", "Year", "Quarter", "Month", "MonthName", "Day", "Weekday"]]

def build_dim_product(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo DimProduct. Vì 1 StockCode có thể có nhiều Description khác nhau
    (lỗi nhập liệu)-> lấy mô tả phổ biến nhất.
    """
    desc_mode = (
        df.groupby("StockCode")["Description"]
        .agg(lambda x: x.value_counts().idxmax())
        .reset_index()
    )
    desc_mode["ProductID"] = range(1, len(desc_mode) + 1)

    return desc_mode[["ProductID", "StockCode", "Description"]]


def build_dim_customer(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo DimCustomer. Một số ít CustomerID gắn với >1 quốc gia
    -> lấy quốc gia xuất hiện nhiều nhất làm quốc gia chính.
    """
    country_mode = (
        df.groupby("CustomerID")["Country"]
        .agg(lambda x: x.value_counts().idxmax())
        .reset_index()
    )
    country_mode.rename(columns={"CustomerID": "CustomerKey"}, inplace=True)
    # Đánh dấu khách hàng ẩn danh
    country_mode["CustomerLabel"] = np.where(
        country_mode["CustomerKey"] == -1, "Unknown Customer",
        "Customer #" + country_mode["CustomerKey"].astype(str)
    )
    return country_mode[["CustomerKey", "CustomerLabel", "Country"]]


def build_dim_country(df: pd.DataFrame) -> pd.DataFrame:
    """Tạo DimCountry (danh sách quốc gia duy nhất)."""
    countries = pd.DataFrame({"Country": df["Country"].unique()}).sort_values("Country")
    countries["CountryID"] = range(1, len(countries) + 1)
    return countries[["CountryID", "Country"]]


def build_fact_sales(df, dim_product, dim_country) -> pd.DataFrame:
    """
    Tạo FactSales bằng cách join với các bảng Dim để lấy khóa ngoại (surrogate key).
    """
    fact = df[df["IsCancelled"] == 0].copy()
    fact["DateID"] = fact["InvoiceDate"].dt.strftime("%Y%m%d").astype(int)
    fact["InvoiceDateTime"] = fact["InvoiceDate"]

    fact = fact.merge(dim_product[["ProductID", "StockCode"]], on="StockCode", how="left")
    fact = fact.merge(dim_country[["CountryID", "Country"]], on="Country", how="left")

    fact = fact.rename(columns={"CustomerID": "CustomerKey"})

    fact["SalesID"] = range(1, len(fact) + 1)

    return fact[[
        "SalesID", "InvoiceNo", "ProductID", "CustomerKey", "DateID", "CountryID",
        "InvoiceDateTime", "Quantity", "UnitPrice", "Revenue",
    ]]
def build_fact_returns(df, dim_product, dim_country):
    returns = df[df["IsCancelled"] == 1].copy()

    returns["DateID"] = (returns["InvoiceDate"].dt.strftime("%Y%m%d").astype(int))
    returns["InvoiceDateTime"] = returns["InvoiceDate"]

    returns = returns.merge(dim_product[["ProductID", "StockCode"]],on="StockCode",how="left")

    returns = returns.merge(dim_country[["CountryID", "Country"]],on="Country",how="left")

    returns = returns.rename(columns={"CustomerID": "CustomerKey"})

    returns["ReturnID"] = range(1, len(returns) + 1)

    # Đổi Quantity và ReturnValue về số dương để dễ phân tích
    returns["ReturnQuantity"] = returns["Quantity"].abs()
    returns["ReturnValue"] = (returns["ReturnQuantity"] * returns["UnitPrice"])

    return returns[[
        "ReturnID", "InvoiceNo", "ProductID", "CustomerKey", "DateID", "CountryID",
        "InvoiceDateTime", "ReturnQuantity", "UnitPrice", "ReturnValue"
        ]]

def load_to_csv(tables: dict, out_dir: str):
    """Bước 3a: Ghi các bảng ra CSV để import trực tiếp vào Power BI."""
    for name, table in tables.items():
        path = os.path.join(out_dir, f"{name}.csv")
        table.to_csv(path, index=False)
        print(f"[LOAD-CSV] {name}: {len(table):,} dòng -> {path}")


def load_to_sqlserver(tables: dict, connection_string: str):
    """
    Nạp dữ liệu vào SQL Server thật.
    LƯU Ý: Các bảng (DimDate, DimProduct, DimCustomer, DimCountry, FactSales)
    phải đã được TẠO SẴN bằng file ddl_star_schema.sql trước khi chạy hàm này
    (dùng if_exists="append" để không xóa cấu trúc bảng + ràng buộc khóa ngoại
    đã định nghĩa trong DDL).

    Thứ tự nạp: Dimension TRƯỚC, Fact SAU - vì FactSales có khóa ngoại
    tham chiếu đến các bảng Dim, nạp sai thứ tự sẽ vi phạm ràng buộc FK.
    """
    engine = create_engine(connection_string)

    load_order = ["DimDate", "DimProduct", "DimCustomer", "DimCountry", "FactSales",  "FactReturns"]

    with engine.begin() as conn:
        for name in load_order:
            table = tables[name]
            # chunksize: nạp theo từng lô 2.000 dòng thay vì gộp toàn bộ bảng
            # thành 1 lệnh INSERT duy nhất - tránh MemoryError với bảng lớn
            # như FactSales (536K+ dòng)
            table.to_sql(name, conn, if_exists="append", index=False, chunksize=5000)
            print(f"[LOAD-SQLSERVER] {name}: {len(table):,} dòng đã nạp vào {SQL_DATABASE_NAME}")


def main():
    # 1. EXTRACT
    df_raw = extract(INPUT_FILE)

    # 2. TRANSFORM
    df_clean = clean(df_raw)

    dim_date = build_dim_date(df_clean)
    dim_product = build_dim_product(df_clean)
    dim_customer = build_dim_customer(df_clean)
    dim_country = build_dim_country(df_clean)
    fact_sales = build_fact_sales(df_clean, dim_product, dim_country)
    fact_returns = build_fact_returns(df_clean, dim_product, dim_country)
    

    tables = {
        "DimDate": dim_date,
        "DimProduct": dim_product,
        "DimCustomer": dim_customer,
        "DimCountry": dim_country,
        "FactSales": fact_sales,
        "FactReturns": fact_returns,
    }

    # 3. LOAD
    load_to_csv(tables, OUTPUT_DIR)
    load_to_sqlserver(tables, CONNECTION_STRING)

    # Thống kê nhanh để kiểm tra kết quả
    print("\n=== KIỂM TRA NHANH ===")
    
    gross_revenue = fact_sales["Revenue"].sum()
    return_value = fact_returns["ReturnValue"].sum()
    net_revenue = gross_revenue - return_value
 
    print("Doanh thu gộp (Gross Revenue)     :", f"{gross_revenue:,.2f}")
    print("Giá trị hàng bị hủy/trả           :", f"{return_value:,.2f}")
    print("Doanh thu thuần (Net Revenue)     :", f"{net_revenue:,.2f}")
    print("Số sản phẩm (DimProduct)          :", len(dim_product))
    print("Số khách hàng (DimCustomer)       :", len(dim_customer))
    print("Số quốc gia (DimCountry)          :", len(dim_country))
    print("Số ngày (DimDate)                 :", len(dim_date))
    print("\nSố dòng FactSales   :", len(fact_sales))
    print("Số dòng FactReturns :", len(fact_returns))
    print("Min InvoiceDate:", df_clean["InvoiceDate"].min())
    print("Max InvoiceDate:", df_clean["InvoiceDate"].max())

if __name__ == "__main__":
    main()