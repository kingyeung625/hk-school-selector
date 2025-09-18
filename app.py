import streamlit as st
import pandas as pd
import plotly.express as px
import re
import os

# --- Streamlit 應用程式介面 ---
st.set_page_config(page_title="學校選校器", layout="centered")
st.title('🏫 學校選校器 (最終穩定版)')
st.write("請先上傳您最新的學校資料檔案，然後使用下方的篩選器來尋找心儀的學校。")

# --- 文字處理函式 ---
def format_and_highlight_text(text, keywords):
    text_str = str(text).strip()
    if not text_str: return ""
    list_marker_pattern = re.compile(r'(\s*[（(]?\d+[.)）]\s*|\s*[①②③④⑤⑥⑦⑧⑨⑩]\s*)')
    parts = list_marker_pattern.split(text_str)
    html_output = f'<p style="margin:0; padding:0;">{parts[0]}'
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            marker = parts[i].strip(); content = parts[i+1].strip()
            html_output += f'<div style="margin-left: 2em; text-indent: -2em; padding-top: 5px;">{marker} {content}</div>'
    html_output += '</p>'
    if keywords:
        pattern = '|'.join([re.escape(keyword) for keyword in keywords])
        html_output = re.sub(
            pattern, 
            lambda match: f'<span style="background-color: yellow;">{match.group(0)}</span>', 
            html_output, 
            flags=re.IGNORECASE
        )
    return html_output

# --- 核心功能函式 (處理資料) ---
@st.cache_data
def process_dataframe(df):
    # 建立一個統一的“特色”欄位用於關鍵字搜尋
    text_columns_for_features = [
        '學校關注事項', '學習和教學策略', '小學教育課程更新重點的發展', '共通能力的培養', '正確價值觀、態度和行為的培養',
        '全校參與照顧學生的多樣性', '全校參與模式融合教育', '非華語學生的教育支援', '課程剪裁及調適措施',
        '家校合作', '校風', '學校發展計劃', '教師專業培訓及發展', '其他未來發展', '辦學宗旨', '全方位學習', '特別室', '其他學校設施'
    ]
    existing_feature_columns = [col for col in text_columns_for_features if col in df.columns]
    df['features_text'] = df[existing_feature_columns].fillna('').astype(str).agg(' '.join, axis=1)

    # 師資百分比處理
    percentage_cols = [
        '已接受師資培訓(佔全校教師人數%)', '學士(佔全校教師人數%)', '碩士、博士或以上 (佔全校教師人數%)', '特殊教育培訓 (佔全校教師人數%)',
        '0-4年資 (佔全校教師人數%)', '5-9年資(佔全校教師人數%)', '10年或以上年資 (佔全校教師人數%)'
    ]
    for col in percentage_cols:
        if col in df.columns:
            s = pd.to_numeric(df[col].astype(str).str.replace('%', '', regex=False), errors='coerce').fillna(0)
            if not s.empty and s.max() > 0 and s.max() <= 1: s = s * 100
            df[col] = s.round(1)

    # 師資及課業次數處理
    numeric_cols = [
        '核准編制教師職位數目', '全校教師總人數', '一年級全年全科測驗次數', '一年級全年全科考試次數',
        '二至六年級全年全科測驗次數', '二至六年級全年全科考試次數'
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            
    # “是/否” 類型欄位處理
    yes_no_cols = {
        '小一上學期以多元化的進展性評估代替測驗及考試': 'p1_no_exam_assessment',
        '避免緊接在長假期後安排測考，讓學生在假期有充分的休息': 'avoid_holiday_exams',
        '按校情靈活編排時間表，盡量在下午安排導修時段，讓學生能在教師指導下完成部分家課': 'afternoon_tutorial',
        '校車服務': 'has_school_bus',
        '家教會': 'has_pta'
    }
    for col, new_name in yes_no_cols.items():
        if col in df.columns:
            df[new_name] = df[col].apply(lambda x: '是' if str(x).strip().lower() in ['有', 'yes'] else '否')

    # 升中關聯學校處理
    feeder_cols = ['一條龍中學', '直屬中學', '聯繫中學']
    existing_feeder_cols = [col for col in feeder_cols if col in df.columns]
    if existing_feeder_cols:
         df['has_feeder_school'] = df[existing_feeder_cols].apply(
            lambda row: '是' if any(pd.notna(val) and str(val).strip() not in ['-', '', '沒有'] for val in row) else '否',
            axis=1
        )
    else:
        df['has_feeder_school'] = '否'
        
    return df

# --- 檔案上傳器 ---
uploaded_file = st.file_uploader("**請上傳您的學校資料檔案 (Excel 或 CSV)**", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'): dataframe = pd.read_csv(uploaded_file, engine='python')
        else: dataframe = pd.read_excel(uploaded_file, engine='openpyxl')
        
        processed_df = process_dataframe(dataframe)
        st.success(f'成功讀取 {len(processed_df)} 筆學校資料！')

        # --- 步驟 2: 建立篩選器 ---
        active_filters = []

        with st.expander("📝 按學校名稱搜尋", expanded=True):
            search_keyword = st.text_input("**輸入學校名稱關鍵字：**")
            if search_keyword: active_filters.append(('name', search_keyword))

        with st.expander("ℹ️ 按學校基本資料搜尋", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                if '學校類別' in processed_df.columns:
                    cat_options = sorted(processed_df['學校類別'].dropna().unique()); selected_cats = st.multiselect("學校類別", options=cat_options)
                    if selected_cats: active_filters.append(('category', selected_cats))
                if '學生性別' in processed_df.columns:
                    gender_options = sorted(processed_df['學生性別'].dropna().unique()); selected_genders = st.multiselect("學生性別", options=gender_options)
                    if selected_genders: active_filters.append(('gender', selected_genders))
                if '宗教' in processed_df.columns:
                    religion_options = sorted(processed_df['宗教'].dropna().unique()); selected_religions = st.multiselect("宗教", options=religion_options)
                    if selected_religions: active_filters.append(('religion', selected_religions))
            with col2:
                if '辦學團體' in processed_df.columns:
                    body_counts = processed_df['辦學團體'].value_counts()
                    body_options = sorted(body_counts[body_counts >= 2].index)
                    selected_bodies = st.multiselect("辦學團體 (只顯示多於一間的團體)", options=body_options)
                    if selected_bodies: active_filters.append(('body', selected_bodies))
                feeder_choice = st.radio("有關聯中學？", ['不限', '是', '否'], horizontal=True, key='feeder')
                if feeder_choice != '不限': active_filters.append(('feeder', feeder_choice))
                bus_choice = st.radio("有校車服務？", ['不限', '是', '否'], horizontal=True, key='bus')
                if bus_choice != '不限': active_filters.append(('bus', bus_choice))
        
        with st.expander("📍 按地區及校網搜尋", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                all_districts = sorted(processed_df['地區'].dropna().unique()); selected_districts = st.multiselect("**選擇地區 (可多選)**", options=all_districts)
                if selected_districts: active_filters.append(('district', selected_districts))
            with col2:
                if selected_districts: available_nets = sorted(processed_df[processed_df['地區'].isin(selected_districts)]['校網'].dropna().unique())
                else: available_nets = sorted(processed_df['校網'].dropna().unique())
                selected_nets = st.multiselect("**選擇校網 (可多選)**", options=available_nets)
                if selected_nets: active_filters.append(('net', selected_nets))

        with st.expander("🌟 按辦學特色搜尋", expanded=False):
            feature_mapping = {"【教學模式與重點】": {"自主學習及探究": ['自主學習', '探究'],"STEAM": ['STEAM', '創客'], "電子學習": ['電子學習', 'e-learning'], "閱讀": ['閱讀'], "資優教育": ['資優'], "專題研習": ['專題研習'], "跨課程學習": ['跨課程'], "兩文三語": ['兩文三語'], "英文教育": ['英文'], "家校合作": ['家校合作'], "境外交流": ['境外交流'], "藝術": ['藝術'], "體育": ['體育']},"【價值觀與品德】": {"中華文化教育": ['中華文化'], "正向、價值觀、生命教育": ['正向', '價值觀', '生命教育'], "國民教育、國安教育": ['國民', '國安'], "服務教育": ['服務'], "關愛及精神健康": ['關愛', '健康']},"【學生支援與發展】": {"全人發展": ['全人發展', '多元發展'], "生涯規劃、啟發潛能": ['生涯規劃', '潛能'], "拔尖補底、照顧差異": ['拔尖補底', '個別差異'], "融合教育": ['融合教育']}}
            col1, col2, col3 = st.columns(3); all_selected_options = []
            with col1: selected1 = st.multiselect("教學模式與重點", options=list(feature_mapping["【教學模式與重點】"].keys())); all_selected_options.extend(selected1)
            with col2: selected2 = st.multiselect("價值觀與品德", options=list(feature_mapping["【價值觀與品德】"].keys())); all_selected_options.extend(selected2)
            with col3: selected3 = st.multiselect("學生支援與發展", options=list(feature_mapping["【學生支援與發展】"].keys())); all_selected_options.extend(selected3)
            if all_selected_options: active_filters.append(('features', all_selected_options))
        
        with st.expander("🎓 按師資條件搜尋", expanded=False):
            slider_options = {'已接受師資培訓(佔全校教師人數%)': '師資培訓比例 (%)', '學士(佔全校教師人數%)': '學士學歷比例 (%)', '碩士、博士或以上 (佔全校教師人數%)': '碩士或以上學歷比例 (%)', '特殊教育培訓 (佔全校教師人數%)': '特殊教育培訓比例 (%)', '0-4年資 (佔全校教師人數%)': '0-4年資比例 (%)', '5-9年資(佔全校教師人數%)': '5-9年資比例 (%)', '10年或以上年資 (佔全校教師人數%)': '10年以上年資比例 (%)'}
            for col_name, slider_label in slider_options.items():
                if col_name in processed
