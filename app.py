import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Мезонин — выкладка", page_icon="📦", layout="centered",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 5rem; max-width: 850px;}
[data-testid="stSidebar"] {min-width: 280px;}
div[data-testid="stMetric"] {background: #f5f7f9; padding: 10px 12px; border-radius: 12px;}
.product-card {border: 1px solid #e5e7eb; border-radius: 14px; padding: 13px 14px; margin: 9px 0; background: white;}
.product-name {font-size: 1.02rem; font-weight: 650; line-height: 1.35; margin-bottom: 8px;}
.product-address {font-size: 1.05rem; font-weight: 700; color: #087f5b; margin: 7px 0;}
.product-meta {font-size: .86rem; color: #626b75; line-height: 1.55;}
div.stButton > button, div.stDownloadButton > button {width:100%; min-height:44px; border-radius:10px;}
div[data-testid="stSelectbox"] label, div[data-testid="stTextInput"] label {font-weight:600;}
@media (max-width: 640px) {
 .block-container {padding-left: .8rem; padding-right: .8rem; padding-top: .7rem;}
 h1 {font-size: 1.55rem !important;}
 h2 {font-size: 1.25rem !important;}
}
</style>
""", unsafe_allow_html=True)

st.title("📦 Мезонин")
st.caption("Мобильная выкладка по товарным группам и адресам")

@st.cache_data
def read_excel(file):
    df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.isna().all()].fillna("")
    for c in df.columns:
        df[c] = df[c].astype(str).replace("nan", "").str.strip()
    return df

DEFAULT_FILE = "1 этаж адрес(1).xlsx"
uploaded = st.file_uploader("Загрузить Excel-базу", type=["xlsx"])
if uploaded:
    df = read_excel(uploaded)
elif Path(DEFAULT_FILE).exists():
    df = read_excel(DEFAULT_FILE)
else:
    st.info("Загрузите Excel-файл с товарами.")
    st.stop()

required = ["Код SKU","Штрих Код","Наименование SKU","Единица измерения",
            "Доступный остаток","Группа","Подгруппа","Торговая марка","Адрес"]
missing = [x for x in required if x not in df.columns]
if missing:
    st.warning("Не найдены колонки: " + ", ".join(missing))

def val(row, col):
    return str(row.get(col, "")).strip()

def row_key(row):
    return val(row,"Код SKU") + "|" + val(row,"Адрес")

if "done_keys" not in st.session_state:
    st.session_state.done_keys = set()

with st.expander("🔎 Поиск и фильтры", expanded=True):
    query = st.text_input("Поиск по SKU, штрихкоду или названию", placeholder="Например: 201964 или сушки")
    group_values = sorted(x for x in df.get("Группа", pd.Series(dtype=str)).unique() if x)
    group = st.selectbox("Товарная группа", ["Все группы"] + group_values)
    f = df.copy()
    if group != "Все группы" and "Группа" in f:
        f = f[f["Группа"] == group]
    sub_values = sorted(x for x in f.get("Подгруппа", pd.Series(dtype=str)).unique() if x)
    sub = st.selectbox("Подгруппа", ["Все подгруппы"] + sub_values)
    if sub != "Все подгруппы" and "Подгруппа" in f:
        f = f[f["Подгруппа"] == sub]
    if query:
        searchable = [c for c in ["Код SKU","Штрих Код","Наименование SKU","Торговая марка","Адрес"] if c in f]
        mask = f[searchable].apply(lambda s: s.str.contains(query, case=False, na=False)).any(axis=1)
        f = f[mask]

total = len(f)
completed = sum(row_key(r) in st.session_state.done_keys for _,r in f.iterrows())
m1,m2,m3 = st.columns(3)
m1.metric("Всего", total)
m2.metric("Готово", completed)
m3.metric("Осталось", total-completed)
if total:
    st.progress(completed/total, text=f"Выполнено {completed} из {total}")

st.subheader("Товары")
page_size = 20
pages = max(1, (total + page_size - 1)//page_size)
if "page" not in st.session_state: st.session_state.page = 1
st.session_state.page = min(st.session_state.page, pages)
p1,p2 = st.columns([1,1])
with p1:
    if st.button("← Назад", disabled=st.session_state.page <= 1):
        st.session_state.page -= 1
        st.rerun()
with p2:
    if st.button("Далее →", disabled=st.session_state.page >= pages):
        st.session_state.page += 1
        st.rerun()
st.caption(f"Страница {st.session_state.page} из {pages} · показано до {page_size} товаров")

start=(st.session_state.page-1)*page_size
page_df=f.iloc[start:start+page_size]
if page_df.empty:
    st.info("По выбранным условиям товары не найдены.")
else:
    for i, (_, r) in enumerate(page_df.iterrows()):
        done = row_key(r) in st.session_state.done_keys
        name = val(r,"Наименование SKU") or "Без наименования"
        address = val(r,"Адрес") or "Адрес не указан"
        status = "✅ Выполнено" if done else "⬜ Не выполнено"
        st.markdown(f"""
        <div class="product-card">
          <div class="product-name">{name}</div>
          <div class="product-address">📍 {address}</div>
          <div class="product-meta">
            SKU: {val(r,'Код SKU')}<br>
            Штрихкод: {val(r,'Штрих Код')}<br>
            Остаток: {val(r,'Доступный остаток')} {val(r,'Единица измерения')}<br>
            Группа: {val(r,'Группа')}<br>
            Подгруппа: {val(r,'Подгруппа')}<br>
            Статус: {status}
          </div>
        </div>
        """, unsafe_allow_html=True)
        if done:
            if st.button("↩ Снять отметку", key=f"undo_{start+i}_{row_key(r)}"):
                st.session_state.done_keys.discard(row_key(r))
                st.rerun()
        else:
            if st.button("✓ Отметить как выполнено", key=f"done_{start+i}_{row_key(r)}", type="primary"):
                st.session_state.done_keys.add(row_key(r))
                st.rerun()

st.divider()
export_cols=[c for c in ["Код SKU","Штрих Код","Наименование SKU","Группа","Подгруппа","Адрес"] if c in df]
report=df[export_cols].copy()
report["Статус"]=report.apply(lambda r:"Выполнено" if row_key(r) in st.session_state.done_keys else "Не выполнено",axis=1)
st.download_button("⬇️ Скачать отчёт по выкладке", report.to_csv(index=False,sep=";",encoding="utf-8-sig").encode("utf-8-sig"),
                   "otchet_vykladka.csv","text/csv")
with st.expander("ℹ️ Важно о сохранении"):
    st.write("В этой версии отметки сохраняются только в текущей сессии браузера. Для общей работы сотрудников и постоянного хранения подключим общую базу данных.")
