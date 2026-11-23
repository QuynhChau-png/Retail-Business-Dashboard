import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# =========================================================
# CẤU HÌNH ĐƯỜNG DẪN
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
file_path = BASE_DIR / "data" / "online_retail.csv"
output_dir = BASE_DIR / "output" / "eda"
output_dir.mkdir(parents=True, exist_ok=True)

# Các mã không phải sản phẩm thật - đồng bộ với ETL
NON_PRODUCT_CODES = [
    "POST",
    "DOT",
    "M",
    "D",
    "BANK CHARGES",
    "CRUK",
    "PADS",
    "C2",
    "AMAZONFEE",
]

# =========================================================
# 1. ĐỌC DỮ LIỆU
# =========================================================

# Đồng bộ encoding với ETL
df = pd.read_csv(file_path, encoding="latin1")

print("\n" + "=" * 70)
print("1. THÔNG TIN TỔNG QUAN DỮ LIỆU")
print("=" * 70)

print("\n===== THÔNG TIN DỮ LIỆU =====")
df.info()

print("\n===== SỐ DÒNG, SỐ CỘT =====")
print("Số dòng:", df.shape[0])
print("Số cột :", df.shape[1])

print("\n===== KIỂU DỮ LIỆU =====")
print(df.dtypes)

# =========================================================
# 2. THỐNG KÊ MÔ TẢ
# =========================================================

print("\n" + "=" * 70)
print("2. THỐNG KÊ MÔ TẢ CÁC BIẾN")
print("=" * 70)

print("\n===== THỐNG KÊ MÔ TẢ BIẾN SỐ =====")
print(df[["Quantity", "UnitPrice", "CustomerID"]].describe())

# =========================================================
# 3. KIỂM TRA GIÁ TRỊ THIẾU
# =========================================================

print("\n" + "=" * 70)
print("3. KIỂM TRA GIÁ TRỊ THIẾU")
print("=" * 70)

missing = pd.DataFrame({
    "MissingCount": df.isnull().sum(),
    "MissingRatePct": (df.isnull().mean() * 100).round(2),
})

print(missing)


# =========================================================
# 4. KHẢO SÁT BIẾN DANH MỤC
# =========================================================

print("\n" + "=" * 70)
print("4. KHẢO SÁT BIẾN DANH MỤC")
print("=" * 70)

print("\n===== TOP 10 QUỐC GIA THEO SỐ DÒNG GIAO DỊCH =====")
print(df["Country"].value_counts().head(10))

print("\n===== SỐ QUỐC GIA =====")
print(df["Country"].nunique())

# =========================================================
# 5. KHẢO SÁT GIÁ TRỊ BẤT THƯỜNG
# =========================================================

print("\n" + "=" * 70)
print("5. KHẢO SÁT GIÁ TRỊ BẤT THƯỜNG")
print("=" * 70)

print("\n===== QUANTITY =====")
print("Số dòng Quantity < 0 :", (df["Quantity"] < 0).sum())
print("Số dòng Quantity = 0 :", (df["Quantity"] == 0).sum())
print("Min Quantity          :", df["Quantity"].min())
print("Max Quantity          :", df["Quantity"].max())

print("\n===== UNIT PRICE =====")
print("Số dòng UnitPrice < 0 :", (df["UnitPrice"] < 0).sum())
print("Số dòng UnitPrice = 0 :", (df["UnitPrice"] == 0).sum())
print("Min UnitPrice         :", df["UnitPrice"].min())
print("Max UnitPrice         :", df["UnitPrice"].max())

print("\n===== GIAO DỊCH HỦY =====")
cancel_mask = df["InvoiceNo"].astype(str).str.startswith("C")
print("Số dòng InvoiceNo bắt đầu bằng C:", cancel_mask.sum())

print("\n===== DÒNG PHI SẢN PHẨM =====")
stockcode_clean = df["StockCode"].astype(str).str.strip().str.upper()
non_product_mask = stockcode_clean.isin(NON_PRODUCT_CODES)
print("Số dòng phi sản phẩm:", non_product_mask.sum())


# =========================================================
# 6. CHUẨN BỊ DỮ LIỆU PHÂN TÍCH
# =========================================================
# Quy tắc làm sạch đồng bộ với ETL:
# - chuẩn hóa ngày
# - chuẩn hóa StockCode
# - loại mã phi sản phẩm
# - chỉ giữ UnitPrice > 0
# - giao dịch bán hợp lệ: Quantity > 0 và InvoiceNo không bắt đầu bằng C

print("\n" + "=" * 70)
print("6. CHUẨN BỊ DỮ LIỆU CHO PHÂN TÍCH")
print("=" * 70)

df_analysis = df.copy()

df_analysis["InvoiceDate"] = pd.to_datetime(
    df_analysis["InvoiceDate"],
    format="mixed",
    dayfirst=True,
    errors="coerce",
)

df_analysis["StockCode"] = (
    df_analysis["StockCode"]
    .astype(str)
    .str.strip()
    .str.upper()
)

# Loại dòng phi sản phẩm
df_analysis = df_analysis[
    ~df_analysis["StockCode"].isin(NON_PRODUCT_CODES)
].copy()

# Loại đơn giá không hợp lệ
df_analysis = df_analysis[
    df_analysis["UnitPrice"] > 0
].copy()

# Chỉ giữ giao dịch bán hợp lệ
df_sales = df_analysis[
    (df_analysis["Quantity"] > 0) &
    (~df_analysis["InvoiceNo"].astype(str).str.startswith("C"))
].copy()

df_sales["Revenue"] = (
    df_sales["Quantity"] * df_sales["UnitPrice"]
)

print("\n===== DỮ LIỆU SAU LỌC =====")
print("Số dòng giao dịch bán hợp lệ:", f"{len(df_sales):,}")
print("Tổng doanh thu bán hợp lệ   :", f"{df_sales['Revenue'].sum():,.2f}")
print(
    "Phạm vi thời gian           :",
    df_sales["InvoiceDate"].min(),
    "->",
    df_sales["InvoiceDate"].max(),
)

# Các biểu đồ phân tích kinh doanh (sản phẩm, quốc gia, thời gian, RFM,
# demand planning...) được xây dựng trên Power BI nên không vẽ lặp lại tại đây.

# =========================================================
# 7. PHÂN TÍCH MỐI QUAN HỆ GIỮA CÁC CHỈ TIÊU THEO SẢN PHẨM
# =========================================================

print("\n" + "=" * 70)
print("7. PHÂN TÍCH TƯƠNG QUAN THEO SẢN PHẨM")
print("=" * 70)

product_analysis = (
    df_sales.groupby("StockCode")
    .agg(
        Quantity=("Quantity", "sum"),
        Orders=("InvoiceNo", "nunique"),
        Revenue=("Revenue", "sum"),
        AvgUnitPrice=("UnitPrice", "mean"),
    )
)

corr_matrix = product_analysis[
    ["Quantity", "Orders", "Revenue", "AvgUnitPrice"]
].corr(method="pearson")

print("\n===== MA TRẬN TƯƠNG QUAN =====")
print(corr_matrix.round(3))

fig, ax = plt.subplots(figsize=(8, 6))

im = ax.imshow(
    corr_matrix,
    vmin=-1,
    vmax=1,
)

labels = [
    "Số lượng bán",
    "Số đơn hàng",
    "Doanh thu",
    "Đơn giá TB",
]

ax.set_xticks(range(len(labels)))
ax.set_yticks(range(len(labels)))
ax.set_xticklabels(labels, rotation=30, ha="right")
ax.set_yticklabels(labels)

for i in range(len(labels)):
    for j in range(len(labels)):
        ax.text(
            j,
            i,
            f"{corr_matrix.iloc[i, j]:.2f}",
            ha="center",
            va="center",
        )

ax.set_title(
    "Ma trận tương quan giữa các chỉ tiêu kinh doanh theo sản phẩm"
)

fig.colorbar(
    im,
    ax=ax,
    label="Hệ số tương quan Pearson",
)

plt.tight_layout()
plt.savefig(
    output_dir / "correlation_matrix.png",
    dpi=300,
    bbox_inches="tight",
)
plt.close()

# =========================================================
# 8. KẾT LUẬN EDA
# =========================================================

print("\n" + "=" * 70)
print("8. KẾT LUẬN EDA")
print("=" * 70)

print(
    """
- Dữ liệu có giá trị thiếu, tập trung chủ yếu ở CustomerID và Description.
- Quantity tồn tại giá trị âm và cực trị lớn; đây là dấu hiệu giao dịch hủy/hoàn trả
  và các trường hợp bất thường cần xử lý riêng.
- UnitPrice tồn tại giá trị không dương và các mức giá cực trị, cần được làm sạch
  trước khi tính doanh thu.
- Một số StockCode đại diện cho phí/điều chỉnh chứ không phải sản phẩm thật,
  cần loại khỏi phân tích sản phẩm.
- Sau tiền xử lý, chỉ sử dụng giao dịch bán hợp lệ để phân tích doanh thu.
- Phân tích tương quan được thực hiện ở cấp sản phẩm nhằm đánh giá mối liên hệ
  giữa số lượng bán, số đơn hàng, doanh thu và đơn giá trung bình.
"""
)

print("Đã lưu ma trận tương quan phục vụ phân tích chẩn đoán tại:", output_dir)
