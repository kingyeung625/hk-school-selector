import streamlit as st
import pandas as pd
import plotly.express as px
import re
import os
import requests
from bs4 import BeautifulSoup

# --- Streamlit 應用程式介面 ---
st.set_page_config(page_title="「01教育」小學概覽搜尋器", layout="centered")
st.title('「01教育」小學概覽搜尋器')
st.markdown(
    '<div style="border: 2px dashed #cccccc; padding: 20px; text-align: center; margin-top: 20px; margin-bottom: 20px;">廣告空間</div>',
    unsafe_allow_html=True
)
st.write("使用下方的篩選器來尋找心儀的學校。")

# --- 初始化 Session State ---
if 'page' not in st.session_state:
    st.session_state.page = 0
if 'active_filters_cache' not in st.session_state:
    st.session_state.active_filters_cache = None

# --- 獲取文章 Meta Data 的快取函式 ---
@st.cache_data(ttl=3600)
def get_article_metadata(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            return og_image['content']
    except requests.RequestException as e:
        # st.error(f"無法獲取文章圖片: {e}")
        return None
    return None

# --- 資料載入與處理 ---
@st.cache_data
def process_dataframe():
    # 改為讀取本地端 CSV 檔案
    df_school_info = pd.read_csv("database.xlsx - 學校資料.csv")
    df_articles = pd.read_csv("database.xlsx - 相關文章.csv")
    df_school_net = pd.read_csv("database.xlsx - 校網資料.csv")

    # 數據合併
    df = pd.merge(df_school_info, df_articles, on='學校名稱', how='left')
    df = pd.merge(df, df_school_net[['學校名稱', '地區', '校網']], on='學校名稱', how='left')

    # 數據清洗與轉換
    df.fillna('-', inplace=True)
    df.replace('--', '-', inplace=True)
    df.replace('沒有', '-', inplace=True)
    df.replace('不適用', '-', inplace=True)

    # 建立全文搜尋欄位
    text_columns = df.columns.drop(['學校名稱', '文章標題', '文章連結'])
    df['full_text_search'] = df[text_columns].astype(str).agg(' '.join, axis=1)

    # 建立學校特色搜尋欄位
    feature_cols = [
        '學校特色', '辦學宗旨', '校訓', '教學模式', '校本課程', '關鍵項目的發展',
        '全方位學習', '學校設施', '其他學習經歷', '學與教策略'
    ]
    for col in feature_cols:
        if col not in df.columns:
            df[col] = ''
    df['features_text'] = df[feature_cols].astype(str).agg(' '.join, axis=1)

    # 處理百分比欄位
    percentage_cols = [
        '上學年已接受師資培訓人數百分率', '上學年學士人數百分率', '上學年碩士_博士或以上人數百分率',
        '上學年特殊教育培訓人數百分率', '上學年0至4年年資人數百分率',
        '上學年5至9年年資人數百分率', '上學年10年年資或以上人數百分率'
    ]
    for col in percentage_cols:
        df[col] = df[col].astype(str).str.replace('%', '').replace('-', '0').astype(float)

    # 建立衍生的特色欄位
    df['p1_no_exam_assessment'] = df['小一測驗及考試次數'].apply(lambda x: '是' if str(x) in ['0', '0-0'] else '否')
    df['avoid_holiday_exams'] = df['測考及學習調適措施'].str.contains('避免在假期後舉行測驗或考試', na=False).map({True: '是', False: '否'})
    df['afternoon_tutorial'] = df['支援學生的學業及個人發展的措施'].str.contains('設有下午功課輔導班', na=False).map({True: '是', False: '否'})
    df['has_pta'] = df['家長教師會'].apply(lambda x: '是' if x == '有' else '否')
    df['has_school_bus'] = df['校車'].apply(lambda x: '是' if x == '校車服務' else '否')
    df['has_feeder_school'] = df.apply(lambda row: '是' if row['一條龍中學'] != '-' or row['直屬中學'] != '-' or row['聯繫中學'] != '-' else '否', axis=1)

    # 標準化學校類別
    def standardize_category(row):
        if '資助' in row['學校類別1']: return '資助'
        if '直資' in row['學校類別1']: return '直資'
        if '私立' in row['學校類別1']: return '私立'
        if '官立' in row['學校類別1']: return '官立'
        return '其他'
    df['學校類別'] = df.apply(standardize_category, axis=1)

    return df

processed_df = process_dataframe()

# --- 篩選器 UI ---
with st.expander("按學校名稱搜尋", expanded=True):
    st.text_input("輸入學校名稱關鍵字", key="school_name_search")

with st.expander("基本資料篩選"):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.multiselect("學校類別", options=sorted(processed_df['學校類別'].unique()), key="school_category")
        st.multiselect("學生性別", options=sorted(processed_df['學生性別'].unique()), key="gender_options")
    with col2:
        st.multiselect("宗教", options=sorted(processed_df['宗教'].unique()), key="religion")
        st.multiselect("地區", options=sorted(processed_df['地區'].unique()), key="district")
    with col3:
        st.multiselect("校網", options=sorted(processed_df['校網'].unique()), key="school_net")

with st.expander("學校特色篩選"):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.radio("設有校車服務", ('全部', '是', '否'), key="has_school_bus_filter", horizontal=True)
        st.radio("設有一條龍/直屬/聯繫中學", ('全部', '是', '否'), key="has_feeder_school_filter", horizontal=True)
    with col2:
        st.radio("設有家長教師會", ('全部', '是', '否'), key="has_pta_filter", horizontal=True)
        st.radio("小一不設測考", ('全部', '是', '否'), key="p1_no_exam_filter", horizontal=True)
    with col3:
        st.radio("設下午功課輔導班", ('全部', '是', '否'), key="afternoon_tutorial_filter", horizontal=True)
        st.radio("避免假期後測考", ('全部', '是', '否'), key="avoid_holiday_exams_filter", horizontal=True)

with st.expander("學校介紹關鍵字"):
    st.text_input("在學校特色、辦學宗旨、教學模式等欄位中搜尋關鍵字", key="features_text_search")

with st.expander("師資條件"):
    st.slider("碩士/博士或以上學歷教師比例 (%)", 0, 100, (0, 100), key="master_doctor_ratio")
    st.slider("10年或以上年資教師比例 (%)", 0, 100, (0, 100), key="senior_teacher_ratio")

with st.expander("班級數目"):
    st.slider("總班數", 0, int(processed_df['上學年總班數'].replace('-', '0').astype(int).max()), (0, 100), key="total_classes")

# --- 重設篩選器功能 ---
def reset_filters():
    st.session_state.school_name_search = ""
    st.session_state.school_category = []
    st.session_state.gender_options = []
    st.session_state.religion = []
    st.session_state.district = []
    st.session_state.school_net = []
    st.session_state.has_school_bus_filter = "全部"
    st.session_state.has_feeder_school_filter = "全部"
    st.session_state.has_pta_filter = "全部"
    st.session_state.p1_no_exam_filter = "全部"
    st.session_state.afternoon_tutorial_filter = "全部"
    st.session_state.avoid_holiday_exams_filter = "全部"
    st.session_state.features_text_search = ""
    st.session_state.master_doctor_ratio = (0, 100)
    st.session_state.senior_teacher_ratio = (0, 100)
    st.session_state.total_classes = (0, 100)
    st.session_state.page = 0
    st.session_state.active_filters_cache = None

# --- 搜尋按鈕 ---
col1, col2 = st.columns([1, 1])
with col1:
    search_button = st.button("🔍 搜尋", type="primary", use_container_width=True)
with col2:
    st.button("🔄 重設", on_click=reset_filters, use_container_width=True)

# --- 執行搜尋與顯示結果 ---
if search_button or st.session_state.active_filters_cache:
    active_filters = []
    if st.session_state.school_name_search:
        active_filters.append({'type': 'school_name', 'value': st.session_state.school_name_search})
    if st.session_state.school_category:
        active_filters.append({'type': 'school_category', 'value': st.session_state.school_category})
    if st.session_state.gender_options:
        active_filters.append({'type': 'gender', 'value': st.session_state.gender_options})
    if st.session_state.religion:
        active_filters.append({'type': 'religion', 'value': st.session_state.religion})
    if st.session_state.district:
        active_filters.append({'type': 'district', 'value': st.session_state.district})
    if st.session_state.school_net:
        active_filters.append({'type': 'school_net', 'value': st.session_state.school_net})
    if st.session_state.has_school_bus_filter != "全部":
        active_filters.append({'type': 'has_school_bus', 'value': st.session_state.has_school_bus_filter})
    if st.session_state.has_feeder_school_filter != "全部":
        active_filters.append({'type': 'has_feeder_school', 'value': st.session_state.has_feeder_school_filter})
    if st.session_state.has_pta_filter != "全部":
        active_filters.append({'type': 'has_pta', 'value': st.session_state.has_pta_filter})
    if st.session_state.p1_no_exam_filter != "全部":
        active_filters.append({'type': 'p1_no_exam', 'value': st.session_state.p1_no_exam_filter})
    if st.session_state.afternoon_tutorial_filter != "全部":
        active_filters.append({'type': 'afternoon_tutorial', 'value': st.session_state.afternoon_tutorial_filter})
    if st.session_state.avoid_holiday_exams_filter != "全部":
        active_filters.append({'type': 'avoid_holiday_exams', 'value': st.session_state.avoid_holiday_exams_filter})
    if st.session_state.features_text_search:
        active_filters.append({'type': 'features_text', 'value': st.session_state.features_text_search})
    if st.session_state.master_doctor_ratio != (0, 100):
        active_filters.append({'type': 'master_doctor_ratio', 'value': st.session_state.master_doctor_ratio})
    if st.session_state.senior_teacher_ratio != (0, 100):
        active_filters.append({'type': 'senior_teacher_ratio', 'value': st.session_state.senior_teacher_ratio})
    if st.session_state.total_classes != (0, 100):
        active_filters.append({'type': 'total_classes', 'value': st.session_state.total_classes})
    
    # 快取篩選條件
    if search_button:
        st.session_state.active_filters_cache = active_filters
        st.session_state.page = 0 # 重置頁碼
    else:
        active_filters = st.session_state.active_filters_cache

    filtered_df = processed_df.copy()
    for f in active_filters:
        if f['type'] == 'school_name':
            filtered_df = filtered_df[filtered_df['學校名稱'].str.contains(f['value'], case=False)]
        elif f['type'] == 'school_category':
            filtered_df = filtered_df[filtered_df['學校類別'].isin(f['value'])]
        elif f['type'] == 'gender':
            filtered_df = filtered_df[filtered_df['學生性別'].isin(f['value'])]
        elif f['type'] == 'religion':
            filtered_df = filtered_df[filtered_df['宗教'].isin(f['value'])]
        elif f['type'] == 'district':
            filtered_df = filtered_df[filtered_df['地區'].isin(f['value'])]
        elif f['type'] == 'school_net':
            filtered_df = filtered_df[filtered_df['校網'].isin(f['value'])]
        elif f['type'] == 'has_school_bus':
            filtered_df = filtered_df[filtered_df['has_school_bus'] == f['value']]
        elif f['type'] == 'has_feeder_school':
            filtered_df = filtered_df[filtered_df['has_feeder_school'] == f['value']]
        elif f['type'] == 'has_pta':
            filtered_df = filtered_df[filtered_df['has_pta'] == f['value']]
        elif f['type'] == 'p1_no_exam':
            filtered_df = filtered_df[filtered_df['p1_no_exam_assessment'] == f['value']]
        elif f['type'] == 'afternoon_tutorial':
            filtered_df = filtered_df[filtered_df['afternoon_tutorial'] == f['value']]
        elif f['type'] == 'avoid_holiday_exams':
            filtered_df = filtered_df[filtered_df['avoid_holiday_exams'] == f['value']]
        elif f['type'] == 'features_text':
            filtered_df = filtered_df[filtered_df['features_text'].str.contains(f['value'], case=False, na=False)]
        elif f['type'] == 'master_doctor_ratio':
            filtered_df = filtered_df[filtered_df['上學年碩士_博士或以上人數百分率'].between(f['value'][0], f['value'][1])]
        elif f['type'] == 'senior_teacher_ratio':
            filtered_df = filtered_df[filtered_df['上學年10年年資或以上人數百分率'].between(f['value'][0], f['value'][1])]
        elif f['type'] == 'total_classes':
            filtered_df = filtered_df[filtered_df['上學年總班數'].replace('-', '0').astype(int).between(f['value'][0], f['value'][1])]

    # ==================================================================
    # ===== 新增功能：顯示目前的篩選條件總結 =====
    # ==================================================================
    if active_filters:
        st.markdown("---")
        with st.container(border=True):
            st.subheader("目前的篩選條件：")
            
            filter_labels = {
                'school_name': '學校名稱',
                'school_category': '學校類別',
                'gender': '學生性別',
                'religion': '宗教',
                'district': '地區',
                'school_net': '校網',
                'has_school_bus': '設有校車服務',
                'has_feeder_school': '設有一條龍/直屬/聯繫中學',
                'has_pta': '設有家長教師會',
                'p1_no_exam': '小一不設測考',
                'afternoon_tutorial': '設下午功課輔導班',
                'avoid_holiday_exams': '避免假期後測考',
                'features_text': '介紹關鍵字',
                'master_doctor_ratio': '碩士/博士教師比例',
                'senior_teacher_ratio': '10年以上年資教師比例',
                'total_classes': '總班數'
            }
            
            summary_cols = st.columns(3) # 分三欄顯示，讓版面更緊湊
            col_index = 0

            for f in active_filters:
                label = filter_labels.get(f['type'], f['type'].replace('_', ' ').title())
                value = f['value']
                
                if isinstance(value, list):
                    value_str = ", ".join(map(str, value))
                elif isinstance(value, tuple):
                    if 'ratio' in f['type']: # 處理百分比滑桿
                         value_str = f"{value[0]}% - {value[1]}%"
                    else:
                         value_str = f"{value[0]} - {value[1]}"
                else:
                    value_str = str(value)
                
                with summary_cols[col_index % 3]:
                    st.markdown(f"**{label}:** {value_str}")

                col_index += 1

    # --- 顯示搜尋結果 ---
    st.markdown("---")
    total_schools = len(filtered_df)
    st.success(f"找到 {total_schools} 所符合條件的學校。")

    if total_schools > 0:
        items_per_page = 5
        total_pages = (total_schools + items_per_page - 1) // items_per_page
        
        start_idx = st.session_state.page * items_per_page
        end_idx = start_idx + items_per_page
        
        paginated_df = filtered_df.iloc[start_idx:end_idx]

        def format_and_highlight_text(text, keyword):
            if not isinstance(text, str) or text == '-':
                return "沒有提供相關資料。"
            
            # 將分點符號（如數字、破折號）轉換為列表項目
            text = re.sub(r'(\d+\.)', r'\n- \1', text)
            text = text.replace('。', '。\n- ')
            
            if keyword:
                try:
                    text = re.sub(f"({re.escape(keyword)})", r"<mark>\1</mark>", text, flags=re.IGNORECASE)
                except re.error:
                    pass # 忽略無效的正則表達式
            
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            formatted_lines = [f"<li>{line.replace('- ', '', 1)}</li>" for line in lines if not line.startswith('- ')]
            formatted_lines += [f"<li>{line.replace('- ', '', 1)}</li>" for line in lines if line.startswith('- ')]
            
            return f"<ul>{''.join(formatted_lines)}</ul>" if formatted_lines else "沒有提供相關資料。"

        for index, row in paginated_df.iterrows():
            st.markdown(f"### {row['學校名稱']}")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.write(f"**地區:** {row['地區']}")
                st.write(f"**校網:** {row['校網']}")
                st.write(f"**學校類別:** {row['學校類別']}")
                st.write(f"**學生性別:** {row['學生性別']}")
                st.write(f"**宗教:** {row['宗教']}")
                
            with col2:
                if row['文章標題'] != '-':
                    st.write(f"**相關文章:**")
                    article_url = row['文章連結']
                    image_url = get_article_metadata(article_url)
                    
                    if image_url:
                        img_col, title_col = st.columns([1, 3])
                        with img_col:
                            st.image(image_url, width=100)
                        with title_col:
                            st.markdown(f"[{row['文章標題']}]({article_url})")
                    else:
                        st.markdown(f"[{row['文章標題']}]({article_url})")
            
            with st.expander("顯示/隱藏詳細資料"):
                st.markdown("<h5>辦學宗旨</h5>", unsafe_allow_html=True)
                st.markdown(format_and_highlight_text(row.get('辦學宗旨'), st.session_state.get('features_text_search')), unsafe_allow_html=True)
                
                st.markdown("<h5>師資資料 (2023/24學年)</h5>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                c1.metric("碩士/博士或以上學歷", f"{row['上學年碩士_博士或以上人數百分率']}%")
                c2.metric("10年或以上年資", f"{row['上學年10年年資或以上人數百分率']}%")
                c3.metric("總班級數量", f"{row['上學年總班數']}")

                st.markdown("<h5>學校特色</h5>", unsafe_allow_html=True)
                st.markdown(format_and_highlight_text(row.get('學校特色'), st.session_state.get('features_text_search')), unsafe_allow_html=True)

            st.markdown("---")
            
        # --- 分頁導航 ---
        if total_pages > 1:
            st.markdown(
                f"<div style='text-align: center; font-size: 1.1em;'>頁數: {st.session_state.page + 1} / {total_pages}</div>",
                unsafe_allow_html=True
            )

            prev_col, page_select_col, next_col = st.columns([2, 3, 2])

            with prev_col:
                if st.session_state.page > 0:
                    st.button("⬅️ 上一頁", on_click=lambda: st.session_state.update(page=st.session_state.page - 1), key=f"prev_{st.session_state.page}", use_container_width=True)

            with page_select_col:
                page_options = range(1, total_pages + 1)
                current_page_selection = st.selectbox(
                    "跳至頁數",
                    options=page_options,
                    index=st.session_state.page,
                    label_visibility="collapsed"
                )
                if (current_page_selection - 1) != st.session_state.page:
                    st.session_state.page = current_page_selection - 1
                    st.rerun()

            with next_col:
                if st.session_state.page < total_pages - 1:
                    st.button("下一頁 ➡️", on_click=lambda: st.session_state.update(page=st.session_state.page + 1), key=f"next_{st.session_state.page}", use_container_width=True)
