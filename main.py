import calendar
from datetime import date

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


st.set_page_config(
    page_title="우리 학교 한 달 급식 칼로리",
    page_icon="🍚",
    layout="wide",
)

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
BASE_URL = "https://open.neis.go.kr/hub"

EDUCATION_OFFICES = {
    "서울특별시교육청": "B10",
    "부산광역시교육청": "C10",
    "대구광역시교육청": "D10",
    "인천광역시교육청": "E10",
    "광주광역시교육청": "F10",
    "대전광역시교육청": "G10",
    "울산광역시교육청": "H10",
    "세종특별자치시교육청": "I10",
    "경기도교육청": "J10",
    "강원특별자치도교육청": "K10",
    "충청북도교육청": "M10",
    "충청남도교육청": "N10",
    "전북특별자치도교육청": "P10",
    "전라남도교육청": "Q10",
    "경상북도교육청": "R10",
    "경상남도교육청": "S10",
    "제주특별자치도교육청": "T10",
}

MEAL_CODES = {
    "아침": "1",
    "점심": "2",
    "저녁": "3",
}


# ------------------------------------------------------------
# 함수
# ------------------------------------------------------------
def get_api_key():
    """Streamlit Secrets에서 NEIS API 키를 읽습니다."""
    try:
        key = st.secrets["NEIS_KEY"]
    except Exception:
        return None

    return str(key).strip()


@st.cache_data(ttl=3600)
def get_all_schools(api_key, office_code):
    url = f"{BASE_URL}/schoolInfo"
    rows=[]; page=1; page_size=1000
    while True:
        params={"KEY":api_key,"Type":"json","pIndex":page,"pSize":page_size,"ATPT_OFCDC_SC_CODE":office_code}
        r=requests.get(url,params=params,timeout=20); r.raise_for_status(); data=r.json()
        if "schoolInfo" not in data or len(data["schoolInfo"])<2: break
        part=data["schoolInfo"][1].get("row",[])
        if not part: break
        rows.extend(part)
        if len(part)<page_size or page>=20: break
        page+=1
    if not rows: return pd.DataFrame()
    df=pd.DataFrame(rows)
    wanted=["ATPT_OFCDC_SC_CODE","ATPT_OFCDC_SC_NM","SD_SCHUL_CODE","SCHUL_NM","SCHUL_KND_SC_NM","LCTN_SC_NM","ORG_RDNMA"]
    for col in wanted:
        if col not in df.columns: df[col]=""
    return df[wanted].drop_duplicates("SD_SCHUL_CODE").reset_index(drop=True)

def filter_schools(schools, keyword):
    key=keyword.strip().lower()
    if not key: return pd.DataFrame()
    return schools[schools["SCHUL_NM"].astype(str).str.lower().str.contains(key,regex=False,na=False)].copy()

@st.cache_data(ttl=1800)
def get_meals(api_key, office_code, school_code, start_date, end_date, meal_code):
    """선택한 학교의 기간별 급식 정보를 가져옵니다."""
    url = f"{BASE_URL}/mealServiceDietInfo"
    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": 1,
        "pSize": 100,
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MLSV_FROM_YMD": start_date,
        "MLSV_TO_YMD": end_date,
        "MMEAL_SC_CODE": meal_code,
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    if "mealServiceDietInfo" not in data:
        return pd.DataFrame()

    rows = data["mealServiceDietInfo"][1].get("row", [])
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # 필요한 열이 없더라도 앱이 깨지지 않도록 처리
    for col in ["MLSV_YMD", "DDISH_NM", "CAL_INFO", "NTR_INFO"]:
        if col not in df.columns:
            df[col] = ""

    df["날짜"] = pd.to_datetime(df["MLSV_YMD"], format="%Y%m%d", errors="coerce")
    df["칼로리(kcal)"] = (
        df["CAL_INFO"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.extract(r"([\d.]+)", expand=False)
    )
    df["칼로리(kcal)"] = pd.to_numeric(df["칼로리(kcal)"], errors="coerce")

    df = df.dropna(subset=["날짜", "칼로리(kcal)"]).copy()
    df = df.sort_values("날짜")

    return df


# ------------------------------------------------------------
# 화면
# ------------------------------------------------------------
st.title("🍚 우리 학교 한 달 급식 칼로리")
st.caption("나이스(NEIS) 학교급식 데이터를 이용해 한 달 급식의 평균 칼로리를 확인합니다.")

st.info(
    "학교를 선택하고 월과 식사 종류를 고르면, 해당 기간에 급식 칼로리 정보가 있는 날짜를 기준으로 평균을 계산합니다."
)

api_key = get_api_key()

if not api_key:
    st.error("NEIS API 키가 없습니다.")
    st.markdown(
        """
**Streamlit Cloud 설정 방법**

1. 나이스 교육정보 개방 포털에서 Open API 인증키를 발급받습니다.
2. Streamlit Cloud의 **Settings → Secrets**로 이동합니다.
3. 아래처럼 입력합니다.

```toml
NEIS_KEY = "발급받은_인증키"
```

키는 `main.py`에 직접 넣지 마세요.
"""
    )
    st.stop()


# ------------------------------------------------------------
# 학교 선택
# ------------------------------------------------------------
st.subheader("1. 학교 선택")

col1, col2 = st.columns([1, 1])

with col1:
    office_name = st.selectbox(
        "시도교육청",
        list(EDUCATION_OFFICES.keys()),
        index=list(EDUCATION_OFFICES.keys()).index("경기도교육청"),
    )

with col2:
    school_name = st.text_input(
        "학교 이름",
        placeholder="예: ○○고등학교",
    )

search_clicked = st.button("🔎 학교 검색", type="primary", use_container_width=True)

if search_clicked:
    if not school_name.strip():
        st.warning("학교 이름을 입력해주세요.")
        st.stop()
    try:
        with st.spinner("학교 목록을 불러오는 중입니다..."):
            all_schools=get_all_schools(api_key, EDUCATION_OFFICES[office_name])
        st.session_state["schools"]=filter_schools(all_schools, school_name)
    except requests.RequestException:
        st.error("NEIS API에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.")
        st.stop()
    except Exception as e:
        st.error(f"학교 검색 중 오류가 발생했습니다: {e}")
        st.stop()

schools=st.session_state.get("schools",pd.DataFrame())
if schools.empty:
    st.info("학교 이름을 입력하고 **학교 검색** 버튼을 눌러주세요.")
    st.stop()

st.success(f"학교 검색 결과: {len(schools)}곳")
school_options=[]
for idx,row in schools.iterrows():
    label=f"{row['SCHUL_NM']} ({row['SCHUL_KND_SC_NM']})"
    if row.get("ORG_RDNMA",""): label += f" - {row['ORG_RDNMA']}"
    school_options.append((idx,label))
selected_idx=st.selectbox("조회할 학교를 선택하세요.",range(len(school_options)),format_func=lambda i: school_options[i][1])
selected_row=schools.loc[school_options[selected_idx][0]]
selected_school_name=selected_row["SCHUL_NM"]
selected_school_code=selected_row["SD_SCHUL_CODE"]
selected_office_code=selected_row["ATPT_OFCDC_SC_CODE"]

# ------------------------------------------------------------
# 기간 / 식사 선택
# ------------------------------------------------------------
st.subheader("2. 조회할 월과 식사 선택")

col1, col2, col3 = st.columns(3)

today = date.today()

with col1:
    year = st.selectbox(
        "연도",
        range(today.year - 1, today.year + 2),
        index=1,
    )

with col2:
    month = st.selectbox(
        "월",
        range(1, 13),
        index=today.month - 1,
        format_func=lambda x: f"{x}월",
    )

with col3:
    meal_name = st.selectbox(
        "식사 종류",
        list(MEAL_CODES.keys()),
        index=1,
    )


last_day = calendar.monthrange(year, month)[1]
start_date = f"{year}{month:02d}01"
end_date = f"{year}{month:02d}{last_day:02d}"

try:
    with st.spinner("급식 정보를 불러오는 중입니다..."):
        meals = get_meals(
            api_key,
            selected_office_code,
            selected_school_code,
            start_date,
            end_date,
            MEAL_CODES[meal_name],
        )
except requests.RequestException:
    st.error("급식 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    st.stop()
except Exception as e:
    st.error(f"급식 정보를 처리하는 중 오류가 발생했습니다: {e}")
    st.stop()


# ------------------------------------------------------------
# 결과
# ------------------------------------------------------------
st.subheader(f"📊 {selected_school_name} · {year}년 {month}월 {meal_name} 급식")

if meals.empty:
    st.warning(
        f"{year}년 {month}월에 등록된 {meal_name} 급식의 칼로리 정보가 없습니다."
    )
    st.stop()

average_kcal = meals["칼로리(kcal)"].mean()
total_kcal = meals["칼로리(kcal)"].sum()
max_kcal = meals["칼로리(kcal)"].max()
min_kcal = meals["칼로리(kcal)"].min()

c1, c2, c3, c4 = st.columns(4)

c1.metric("한 달 평균", f"{average_kcal:,.0f} kcal")
c2.metric("한 달 총합", f"{total_kcal:,.0f} kcal")
c3.metric("가장 높은 날", f"{max_kcal:,.0f} kcal")
c4.metric("가장 낮은 날", f"{min_kcal:,.0f} kcal")

st.markdown(
    f"**평균 계산에 사용된 급식일:** {len(meals)}일"
)

# 그래프
chart_df = meals[["날짜", "칼로리(kcal)"]].copy()

fig = px.bar(
    chart_df,
    x="날짜",
    y="칼로리(kcal)",
    title=f"{year}년 {month}월 날짜별 {meal_name} 급식 칼로리",
    labels={
        "날짜": "날짜",
        "칼로리(kcal)": "칼로리 (kcal)",
    },
    hover_data={
        "날짜": "|%Y-%m-%d",
        "칼로리(kcal)": ":,.0f",
    },
)

fig.update_layout(
    hovermode="x unified",
    xaxis=dict(tickformat="%m/%d"),
)

st.plotly_chart(fig, use_container_width=True)

# 평균선
avg_fig = px.line(
    chart_df,
    x="날짜",
    y="칼로리(kcal)",
    markers=True,
    title=f"{year}년 {month}월 급식 칼로리 변화",
    labels={
        "날짜": "날짜",
        "칼로리(kcal)": "칼로리 (kcal)",
    },
)

avg_fig.add_hline(
    y=average_kcal,
    line_dash="dash",
    annotation_text=f"월 평균 {average_kcal:,.0f} kcal",
    annotation_position="top left",
)

st.plotly_chart(avg_fig, use_container_width=True)

# 급식표
with st.expander("🍽️ 날짜별 급식 메뉴 보기"):
    table_df = meals[["날짜", "DDISH_NM", "칼로리(kcal)"]].copy()
    table_df["날짜"] = table_df["날짜"].dt.strftime("%Y-%m-%d")
    table_df.columns = ["날짜", "급식 메뉴", "칼로리(kcal)"]

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
    )

st.caption(
    "데이터 출처: 교육부·나이스(NEIS) 교육정보 개방 포털 급식식단정보. "
    "급식 칼로리는 학교가 등록한 급식 데이터를 기준으로 표시됩니다."
)
