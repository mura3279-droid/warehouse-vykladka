import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO

st.set_page_config(page_title="Мезонин — выкладка", page_icon="📦", layout="wide")
st.title("📦 Мезонин — выкладка")
st.caption("Поиск товаров, адресное размещение и контроль выполнения выкладки.")

DEFAULT_FILE = "1 этаж адрес(1).xlsx"

@st.cache_data
def load_excel(file):
    df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    # Remove completely empty columns
    df = df.loc[:, ~df.isna().all()]
    df = df.fillna("")
    return df

uploaded = st.sidebar.file_uploader("Загрузить Excel-базу", type=["xlsx", "xls"])
if uploaded:
    data = load_excel(uploaded)
elif Path(DEFAULT_FILE).exists():
    data = load_excel(DEFAULT_FILE)
else:
    st.info("Загрузите Excel-файл с товарами через левую панель.")
    st.stop()

required = ["Код SKU", "Штрих Код", "Наименование SKU", "Единица измерения",
            "Доступный остаток", "Группа", "Подгруппа", "Торговая марка", "Адрес"]
missing = [c for c in required if c not in data.columns]
if missing:
    st.warning("Не найдены ожидаемые колонки: " + ", ".join(missing) +
               ". Проверьте заголовки Excel или загрузите корректную таблицу.")

# normalize text for filter and display
for col in data.columns:
    data[col] = data[col].astype(str).replace("nan", "").str.strip()

# Working state is kept in this browser session; export allows saving progress
if "done_keys" not in st.session_state:
    st.session_state.done_keys = set()

def key_for(row):
    return str(row.get("Код SKU", "")) + "|" + str(row.get("Адрес", ""))

data["Статус"] = data.apply(lambda r: "✅ Выполнено" if key_for(r) in st.session_state.done_keys else "⬜ Не выполнено", axis=1)

st.sidebar.header("Фильтры")
search = st.sidebar.text_input("Поиск: SKU / штрихкод / название")
group_col = "Группа" if "Группа" in data.columns else None
sub_col = "Подгруппа" if "Подгруппа" in data.columns else None
address_col = "Адрес" if "Адрес" in data.columns else None

filtered = data.copy()
if group_col:
    groups = sorted([x for x in filtered[group_col].unique() if x])
    selected_group = st.sidebar.selectbox("Товарная группа", ["Все группы"] + groups)
    if selected_group != "Все группы":
        filtered = filtered[filtered[group_col] == selected_group]
if sub_col:
    subs = sorted([x for x in filtered[sub_col].unique() if x])
    selected_sub = st.sidebar.selectbox("Подгруппа", ["Все подгруппы"] + subs)
    if selected_sub != "Все подгруппы":
        filtered = filtered[filtered[sub_col] == selected_sub]
if address_col:
    addresses = sorted([x for x in filtered[address_col].unique() if x])
    selected_address = st.sidebar.selectbox("Адрес", ["Все адреса"] + addresses)
    if selected_address != "Все адреса":
        filtered = filtered[filtered[address_col] == selected_address]
if search:
    fields = [c for c in ["Код SKU", "Штрих Код", "Наименование SKU", "Торговая марка", "Адрес"] if c in filtered.columns]
    mask = filtered[fields].astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
    filtered = filtered[mask]

st.subheader("Товары для выкладки")
total = len(filtered)
completed = sum(key_for(r) in st.session_state.done_keys for _, r in filtered.iterrows())
c1,c2,c3 = st.columns(3)
c1.metric("Товарных строк", total)
c2.metric("Выполнено", completed)
c3.metric("Осталось", total-completed)
if total:
    st.progress(completed/total)

columns_to_show = [c for c in required if c in filtered.columns]
view = filtered[columns_to_show + ["Статус"]].copy() if columns_to_show else filtered.copy()
st.dataframe(view, use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("Отметить выкладку")
if total:
    options = filtered.apply(lambda r: f'{r.get("Код SKU","")} | {r.get("Наименование SKU","")} | {r.get("Адрес","")}', axis=1).tolist()
    selected = st.selectbox("Выберите товар/адрес", options)
    idx = options.index(selected)
    row = filtered.iloc[idx]
    row_key = key_for(row)
    is_done = row_key in st.session_state.done_keys
    st.write(f"**SKU:** {row.get('Код SKU','')}  ·  **Адрес:** {row.get('Адрес','')}")
    if is_done:
        if st.button("Снять отметку «Выполнено»"):
            st.session_state.done_keys.discard(row_key)
            st.rerun()
    else:
        if st.button("✅ Отметить как выполнено", type="primary"):
            st.session_state.done_keys.add(row_key)
            st.rerun()
else:
    st.info("По выбранным фильтрам товары не найдены.")

# Export all current completion records
status_export = data[["Код SKU","Наименование SKU","Адрес"]].copy() if all(c in data.columns for c in ["Код SKU","Наименование SKU","Адрес"]) else data.copy()
status_export["Статус"] = status_export.apply(lambda r: "Выполнено" if key_for(r) in st.session_state.done_keys else "Не выполнено", axis=1)
csv_bytes = status_export.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
st.download_button("⬇️ Скачать отчёт по выполнению (CSV)", data=csv_bytes, file_name="отчет_выкладка.csv", mime="text/csv")

with st.expander("Как пользоваться"):
    st.markdown("""
    1. Загрузите Excel-файл через боковую панель (или положите его рядом с `app.py` под именем `1 этаж адрес(1).xlsx`).
    2. Выберите группу, подгруппу и/или адрес.
    3. Найдите товар по SKU, штрихкоду или названию.
    4. Отметьте выполненную выкладку.
    5. Скачайте CSV-отчёт для сохранения отметок.

    **Важно:** текущая версия сохраняет отметки только в активной сессии браузера. Для общей работы нескольких сотрудников с постоянным сохранением потребуется подключить базу данных/SharePoint.
    """)
