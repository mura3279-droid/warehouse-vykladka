
import os, json, sqlite3, hashlib, hmac, re, html
from pathlib import Path
from io import BytesIO
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT=Path(__file__).parent
st.set_page_config(page_title="Мезонин · выкладка",page_icon="📦",layout="wide")
st.markdown("""<style>.block-container{padding-top:1rem;max-width:1150px}.stButton button{border-radius:11px;min-height:42px}</style>""",unsafe_allow_html=True)

DB=ROOT/"mezonin_demo.sqlite3"
def connect():
    c=sqlite3.connect(str(DB),timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS products(
      item_id TEXT PRIMARY KEY, sku TEXT, barcode TEXT, name TEXT, unit TEXT,
      qty TEXT, grp TEXT, subgroup TEXT, brand TEXT, address TEXT,
      alley TEXT, module TEXT, shelf TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS statuses(item_id TEXT PRIMARY KEY,status TEXT NOT NULL DEFAULT 'pending',reason TEXT DEFAULT '')""")
    c.commit()
    return c
def clean(x):
    if pd.isna(x):return ""
    return str(x).strip()
def address_parts(a):
    p=[x.strip() for x in str(a).split(".")]
    return (p[2],p[3],p[4]) if len(p)>=5 else ("","","")
def normalize(rows):
    output=[]
    for r in rows:
        sku=clean(r.get("Код SKU") or r.get("Код товара") or r.get("SKU"))
        bc=clean(r.get("Штрих Код") or r.get("Штрихкод") or r.get("ШК") or r.get("Barcode"))
        name=clean(r.get("Наименование SKU") or r.get("Наименование") or r.get("Название товара"))
        a=clean(r.get("Адрес") or r.get("Адрес хранения") or r.get("Адрес ячейки"))
        if not name or not a: continue
        alley,module,shelf=address_parts(a)
        if not alley or not module:continue
        qty=clean(r.get("Доступный остаток") or r.get("Остаток") or r.get("Количество"))
        fields=(sku,bc,name,clean(r.get("Единица измерения")),qty,clean(r.get("Группа")),clean(r.get("Подгруппа")),clean(r.get("Торговая марка")),a,alley,module,shelf)
        # Unique item at a physical address; duplicate rows of same SKU/address become one task
        key=hashlib.sha256((sku+"|"+a+"|"+bc).encode()).hexdigest()[:24]
        output.append((key,)+fields)
    return list({r[0]:r for r in output}.values())
def import_rows(rows):
    parsed=normalize(rows)
    if not parsed: raise ValueError("Не найдены товары с адресами вида 8031.1.8.5.2")
    c=connect()
    with c:
        c.execute("CREATE TEMP TABLE new_products AS SELECT * FROM products WHERE 0")
        c.executemany("INSERT OR REPLACE INTO new_products VALUES ("+",".join(["?"]*13)+")",parsed)
        c.execute("DELETE FROM products")
        c.execute("INSERT INTO products SELECT * FROM new_products")
        c.execute("DROP TABLE new_products")
        c.execute("DELETE FROM statuses WHERE item_id NOT IN (SELECT item_id FROM products)")
    c.close()
    return len(parsed)
def read_df():
    c=connect()
    df=pd.read_sql_query("""SELECT p.*, COALESCE(s.status,'pending') AS status,
      COALESCE(s.reason,'') AS reason FROM products p LEFT JOIN statuses s ON p.item_id=s.item_id""",c)
    c.close()
    return df
def set_status(item_id,status,reason=""):
    c=connect()
    with c:c.execute("INSERT INTO statuses(item_id,status,reason) VALUES (?,?,?) ON CONFLICT(item_id) DO UPDATE SET status=excluded.status,reason=excluded.reason",(item_id,status,reason))
    c.close()
def secret():
    try: return str(st.secrets["ADMIN_PASSWORD"])
    except Exception: return os.environ.get("ADMIN_PASSWORD","")
if "role" not in st.session_state:st.session_state.role="Сотрудник"
if "admin_ok" not in st.session_state:st.session_state.admin_ok=False
st.title("📦 Мезонин · выкладка товара")
role=st.radio("Режим",["Сотрудник","Администратор"],horizontal=True,key="role")
if role=="Администратор" and not st.session_state.admin_ok:
    password=st.text_input("Пароль администратора",type="password")
    if st.button("Войти"):
        if not secret():st.error("Сначала установите ADMIN_PASSWORD в настройках Streamlit.")
        elif hmac.compare_digest(password,secret()):st.session_state.admin_ok=True;st.rerun()
        else:st.error("Неверный пароль")
    st.stop()
if role=="Администратор" and st.button("Выйти из кабинета"):
    st.session_state.admin_ok=False;st.session_state.role="Сотрудник";st.rerun()
c=connect()
n=c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
c.close()
if not n:
    with open(ROOT/"demo_items.json",encoding="utf-8") as f: n=import_rows(json.load(f))
df=read_df()
if role=="Администратор":
    st.subheader("Панель руководителя")
    st.caption("Отчёт автоматически обновляется каждые 5 секунд, пока вкладка открыта")

    @st.fragment(run_every="5s")
    def live_admin_report():
        latest=read_df()
        total=len(latest)
        done=int((latest.status=="done").sum())
        missing=int((latest.status=="missing").sum())
        pending=total-done-missing
        a,b,c,d=st.columns(4)
        a.metric("Всего адресных позиций",total)
        b.metric("Выставлено",done)
        c.metric("Не выставлено",pending)
        d.metric("Не найдено",missing)
        st.progress(done/max(total,1),text=f"Прогресс: {done/max(total,1):.1%}")
        if total:
            group=latest.groupby("alley",sort=True).agg(
                total=("item_id","count"),
                done=("status",lambda s:(s=="done").sum()),
                missing=("status",lambda s:(s=="missing").sum())
            ).reset_index()
            group["pending"]=group.total-group.done-group.missing
            group["progress_pct"]=(100*group.done/group.total).round(1)
            st.dataframe(group.rename(columns={
                "alley":"Аллея","total":"Всего","done":"Выставлено",
                "missing":"Не найдено","pending":"Не выставлено",
                "progress_pct":"Прогресс, %"
            }),hide_index=True,use_container_width=True)
            st.subheader("Прогресс по модулям")
            by_module=latest.groupby(["alley","module"],sort=True).agg(
                total=("item_id","count"),
                done=("status",lambda s:(s=="done").sum()),
                missing=("status",lambda s:(s=="missing").sum())
            ).reset_index()
            by_module["pending"]=by_module.total-by_module.done-by_module.missing
            by_module["progress_pct"]=(100*by_module.done/by_module.total).round(1)
            st.dataframe(by_module.rename(columns={
                "alley":"Аллея","module":"Модуль","total":"Всего",
                "done":"Выставлено","missing":"Не найдено",
                "pending":"Не выставлено","progress_pct":"Прогресс, %"
            }),hide_index=True,use_container_width=True)
        st.subheader("Проблемные товары")
        problems=latest[latest.status=="missing"][["alley","module","shelf","sku","name","address","reason"]]
        st.dataframe(problems.rename(columns={"alley":"Аллея","module":"Модуль","shelf":"Полка","sku":"Код товара","name":"Товар","address":"Адрес","reason":"Причина"}),hide_index=True,use_container_width=True)
    live_admin_report()
    st.divider()
    st.subheader("Заменить ассортимент из Excel")
    up=st.file_uploader("Файл .xlsx (доступно только администратору)",type=["xlsx"])
    if up is not None and st.button("Подтвердить замену базы",type="primary"):
        try:
            newdf=pd.read_excel(BytesIO(up.getvalue()),dtype=str,keep_default_na=False,engine="openpyxl")
            if not any(k in newdf.columns for k in ("Код SKU","Код товара","SKU")):raise ValueError("Нет столбца «Код товара» / «Код SKU»")
            count=import_rows(newdf.to_dict("records"))
            st.success(f"Загружено {count} адресных позиций. Совпадающие отметки сохранены.")
            st.rerun()
        except Exception as e:st.error(f"Не удалось загрузить файл: {e}")
    st.caption("ТЕСТ: SQLite хранит отметки в текущем экземпляре сервера. На Streamlit Cloud данные могут исчезнуть после перезапуска. Для постоянной работы подключим общую облачную базу.")
    st.stop()

st.caption("Рабочий кабинет сотрудника · демонстрационная база из прежней сборки")
alleys=sorted(df.alley.unique(),key=lambda x:int(x) if x.isdigit() else 999)
alley=st.selectbox("1. Аллея",alleys,index=alleys.index("8") if "8" in alleys else 0)
d1=df[df.alley==alley]
modules=sorted(d1.module.unique(),key=lambda x:int(x) if x.isdigit() else 999)
module=st.selectbox("2. Модуль",modules)
d2=d1[d1.module==module]
shelves=sorted(d2.shelf.unique(),key=lambda x:int(x) if x.isdigit() else 999)
shelf=st.selectbox("3. Полка",["Все полки"]+shelves)
view=d2 if shelf=="Все полки" else d2[d2.shelf==shelf]
total=len(d2);done=int((d2.status=="done").sum());missing=int((d2.status=="missing").sum())
a,b,c=st.columns(3)
a.metric("Всего",total);b.metric("Выставлено",done);c.metric("Осталось",total-done-missing)
st.progress(done/max(total,1),text="Модуль завершён ✅" if done==total and total else f"Модуль: {done}/{total}")
if missing:st.warning(f"Не найдено: {missing} — модуль ещё не завершён")
filter_mode=st.segmented_control("Фильтр",["Все","Не выставлено","Выставлено","Не найдено"],default="Не выставлено")
if filter_mode=="Не выставлено":view=view[view.status=="pending"]
elif filter_mode=="Выставлено":view=view[view.status=="done"]
elif filter_mode=="Не найдено":view=view[view.status=="missing"]
query=st.text_input("Поиск по Barcode, коду или названию",placeholder="Введите или сканируйте штрихкод")
with st.expander("📷 Открыть сканер Barcode"):
    try:
        scanner=components.declare_component("mezonin_barcode_scanner",path=str(ROOT/"scanner"))
        scanned=scanner(key="barcode_scanner",default="")
        if scanned and scanned!=st.session_state.get("last_scan",""):
            st.session_state.last_scan=scanned
            st.session_state.scanned_query=scanned
            st.rerun()
    except Exception as e:st.info(f"Сканер недоступен: {e}. Используйте ручной ввод.")
if st.session_state.get("scanned_query"):
    st.info(f"Последний скан: {st.session_state.scanned_query}")
    if st.button("Показать сканированный товар"):
        st.session_state["search_override"]=st.session_state.scanned_query
search=query.strip() or st.session_state.get("search_override","")
if search:
    view=d1[d1.apply(lambda r:search.lower() in (r["barcode"]+" "+r["sku"]+" "+r["name"]).lower(),axis=1)]
    st.caption("Поиск выполняется по всей выбранной аллее")
st.caption(f"Показано позиций: {len(view)}")
for r in view.head(120).itertuples():
    with st.container(border=True):
        left,right=st.columns([1,3])
        with left:
            sku_photo=re.sub(r"\.0$","",str(r.sku).strip())
            if sku_photo and re.fullmatch(r"[0-9A-Za-z_-]+",sku_photo):
                photo_url=f"https://s3-pic.e-magnum.kz/item/{sku_photo}.jpg"
                # Browser loads image directly. Streamlit's server-side image fetch is avoided.
                st.markdown(
                    f'<div style="min-height:105px;text-align:center">'
                    f'<img src="{html.escape(photo_url,quote=True)}" loading="eager" referrerpolicy="no-referrer" '
                    f'style="width:100%;max-width:160px;max-height:165px;object-fit:contain" '
                    f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\'">'
                    f'<div style="display:none;color:#64748b;font-size:12px;padding:24px 0">Фото отсутствует</div>'
                    f'</div>',unsafe_allow_html=True)
                st.markdown(f"[Открыть фото ↗]({photo_url})")
            else:st.caption("Фото отсутствует")
        with right:
            st.markdown(f"**{r.name}**")
            st.caption(f"Код: {r.sku} · ШК: {r.barcode} · Адрес: {r.address}")
            st.caption(f"Полка {r.shelf} · {r.grp} / {r.subgroup} · Остаток {r.qty} {r.unit}")
            if r.status=="done":st.success("Выставлен")
            elif r.status=="missing":st.error("Не найден: "+r.reason)
            else:st.warning("Не выставлен")
            b1,b2,b3=st.columns(3)
            if b1.button("✓ Выставлен",key="done"+r.item_id):set_status(r.item_id,"done");st.rerun()
            if b2.button("↩ Сбросить",key="reset"+r.item_id):set_status(r.item_id,"pending");st.rerun()
            reason=b3.selectbox("Причина",["Нет на паллете","Не найден на складе","Проблема с адресом"],key="reason"+r.item_id,label_visibility="collapsed")
            if st.button("⚠ Товар не найден",key="missing"+r.item_id):set_status(r.item_id,"missing",reason);st.rerun()
if len(view)>120:st.info("Показаны первые 120 позиций. Выберите полку или используйте поиск.")
