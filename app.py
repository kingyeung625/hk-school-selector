import streamlit as st
import pandas as pd
import plotly.express as px # 【核心改動】引入新的繪圖工具
import platform
import re
import os

# --- Streamlit 應用程式介面 ---

st.set_page_config(page_title="學校選校器", layout="centered")
st.title('🏫 學校選校器')
st.write("請先上傳您的學校資料檔案，然後使用下方的篩選器來尋找心儀的學校。")

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
    # (此函式與之前版本相同)
    text_columns_for_features = [
        '學校關注事項', '學習和教學策略', '小學教育課程更新重點的發展', '共通能力的培養', '正確價值觀、態度和行為的培養',
        '全校參與照顧學生的多樣性', '全校參與模式融合教育', '非華語學生的教育支援', '課程剪裁及調適措施',
        '家校合作', '校風', '學校發展計劃', '教師專業培訓及發展', '其他未來發展', '辦學宗旨', '全方位學習', '特別室', '其他學校設施'
    ]
    existing_feature_columns = [col for col in text_columns_for_features if col in df.columns]
    df['features_text'] = df[existing_feature_columns].fillna('').astype(str).agg(' '.join, axis=1)
    percentage_cols = [
        '已接受師資培訓(佔全校教師人數%)', '學士(佔全校教師人數%)', '碩士、博士或以上 (佔全校教師人數%)', '特殊教育培訓 (佔全校教師人數%)',
        '0-4年資 (佔全校教師人數%)', '5-9年資(佔全校教師人數%)', '10年或以上年資 (佔全校教師人數%)'
    ]
    for col in percentage_cols:
        if col in df.columns:
            s = pd.to_numeric(df[col].astype(str).str.replace('%', '', regex=False), errors='coerce').fillna(0)
            if not s.empty and s.max() > 0 and s.max() <= 1: s = s * 100
            df[col] = s.round(1)
    numeric_cols = [
        '核准編制教師職位數目', '全校教師總人數', '一年級全年全科測驗次數', '一年級全年全科考試次數',
        '二至六年級全年全科測驗次數', '二至六年級全年全科考試次數'
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    yes_no_cols = {
        '小一上學期以多元化的進展性評估代替測驗及考試': 'p1_no_exam_assessment',
        '避免緊接在長假期後安排測考，讓學生在假期有充分的休息': 'avoid_holiday_exams',
        '按校情靈活編排時間表，盡量在下午安排導修時段，讓學生能在教師指導下完成部分家課': 'afternoon_tutorial'
    }
    for col, new_name in yes_no_cols.items():
        if col in df.columns:
            df[new_name] = df[col].apply(lambda x: '是' if str(x).strip() in ['有', 'Yes'] else '否')
    return df

# --- 檔案上傳器 ---
uploaded_file = st.file_uploader("**請上傳您的學校資料檔案 (Excel 或 CSV)**", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'): dataframe = pd.read_csv(uploaded_file, engine='python')
        else: dataframe = pd.read_excel(uploaded_file, engine='openpyxl')
        
        processed_df = process_dataframe(dataframe)
        st.success(f'成功讀取 {len(processed_df)} 筆學校資料！')

        # --- 篩選器部分 (與之前版本相同) ---
        filtered_df = processed_df.copy()
        all_selected_keywords_for_highlight = []
        with st.expander("📝 按學校名稱搜尋", expanded=True):
            search_keyword = st.text_input("**輸入學校名稱關鍵字：**")
            if search_keyword: filtered_df = filtered_df[filtered_df['學校名稱'].str.contains(search_keyword, case=False, na=False)]
        with st.expander("📍 按地區及校網搜尋", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                all_districts = sorted(processed_df['地區'].dropna().unique()); selected_districts = st.multiselect("**選擇地區 (可多選)**", options=all_districts)
                if selected_districts: filtered_df = filtered_df[filtered_df['地區'].isin(selected_districts)]
            with col2:
                if selected_districts: available_nets = sorted(processed_df[processed_df['地區'].isin(selected_districts)]['校網'].dropna().unique())
                else: available_nets = sorted(processed_df['校網'].dropna().unique())
                selected_nets = st.multiselect("**選擇校網 (可多選)**", options=available_nets)
                if selected_nets: filtered_df = filtered_df[filtered_df['校網'].isin(selected_nets)]
        with st.expander("🌟 按辦學特色搜尋", expanded=False):
            feature_mapping = {
                "【教學模式與重點】": {"自主學習及探究": ['自主學習', '探究'], "STEAM": ['STEAM', '創客'], "電子學習": ['電子學習', 'e-learning'], "閱讀": ['閱讀'], "資優教育": ['資優'], "專題研習": ['專題研習'], "跨課程學習": ['跨課程'], "兩文三語": ['兩文三語'], "英文教育": ['英文'], "家校合作": ['家校合作'], "境外交流": ['境外交流'], "藝術": ['藝術'], "體育": ['體育']},
                "【價值觀與品德】": {"中華文化教育": ['中華文化'], "正向、價值觀、生命教育": ['正向', '價值觀', '生命教育'], "國民教育、國安教育": ['國民', '國安'], "服務教育": ['服務'], "關愛及精神健康": ['關愛', '健康']},
                "【學生支援與發展】": {"全人發展": ['全人發展', '多元發展'], "生涯規劃、啟發潛能": ['生涯規劃', '潛能'], "拔尖補底、照顧差異": ['拔尖補底', '個別差異'], "融合教育": ['融合教育']}
            }
            col1, col2, col3 = st.columns(3); all_selected_options = []
            with col1: selected1 = st.multiselect("教學模式與重點", options=list(feature_mapping["【教學模式與重點】"].keys())); all_selected_options.extend(selected1)
            with col2: selected2 = st.multiselect("價值觀與品德", options=list(feature_mapping["【價值觀與品德】"].keys())); all_selected_options.extend(selected2)
            with col3: selected3 = st.multiselect("學生支援與發展", options=list(feature_mapping["【學生支援與發展】"].keys())); all_selected_options.extend(selected3)
            if all_selected_options:
                for option in all_selected_options:
                    search_terms = [];
                    for category in feature_mapping.values():
                        if option in category: search_terms = category[option]; all_selected_keywords_for_highlight.extend(search_terms); break
                    if search_terms:
                        regex_pattern = '|'.join([re.escape(term) for term in search_terms])
                        filtered_df = filtered_df[filtered_df['features_text'].str.contains(regex_pattern, case=False, na=False, regex=True)]
        with st.expander("🎓 按師資條件搜尋", expanded=False):
            st.write("透過滑桿設定您對師資的**最低**要求：")
            slider_options = {'已接受師資培訓(佔全校教師人數%)': '師資培訓比例 (%)', '學士(佔全校教師人數%)': '學士學歷比例 (%)', '碩士、博士或以上 (佔全校教師人數%)': '碩士或以上學歷比例 (%)', '特殊教育培訓 (佔全校教師人數%)': '特殊教育培訓比例 (%)', '0-4年資 (佔全校教師人數%)': '0-4年資比例 (%)', '5-9年資(佔全校教師人數%)': '5-9年資比例 (%)', '10年或以上年資 (佔全校教師人數%)': '10年以上年資比例 (%)'}
            for col_name, slider_label in slider_options.items():
                if col_name in filtered_df.columns:
                    min_val = st.slider(slider_label, 0, 100, 0, 5, key=col_name)
                    if min_val > 0: filtered_df = filtered_df[filtered_df[col_name] >= min_val]
        with st.expander("📚 按課業安排搜尋", expanded=False):
            st.write("選擇您偏好的課業與評估方式：")
            st.markdown("**評估次數**"); col1, col2 = st.columns(2)
            with col1:
                max_p1_tests = st.selectbox('小一全年最多測驗次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p1_test')
                if max_p1_tests != '任何次數': filtered_df = filtered_df[filtered_df['一年級全年全科測驗次數'] <= int(max_p1_tests)]
                max_p2_6_tests = st.selectbox('二至六年級最多測驗次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p2-6_test')
                if max_p2_6_tests != '任何次數': filtered_df = filtered_df[filtered_df['二至六年級全年全科測驗次數'] <= int(max_p2_6_tests)]
            with col2:
                max_p1_exams = st.selectbox('小一全年最多考試次數', options=['任何次數', 0, 1, 2, 3], index=0, key='p1_exam')
                if max_p1_exams != '任何次數': filtered_df = filtered_df[filtered_df['一年級全年全科考試次數'] <= int(max_p1_exams)]
                max_p2_6_exams = st.selectbox('二至六年級最多考試次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p2-6_exam')
                if max_p2_6_exams != '任何次數': filtered_df = filtered_df[filtered_df['二至六年級全年全科考試次數'] <= int(max_p2_6_exams)]
            st.markdown("**其他安排**"); p1_no_exam = st.radio("小一上學期以多元化評估代替測考？", ['不限', '是', '否'], horizontal=True)
            if p1_no_exam != '不限' and 'p1_no_exam_assessment' in filtered_df.columns: filtered_df = filtered_df[filtered_df['p1_no_exam_assessment'] == p1_no_exam]
            avoid_holiday = st.radio("避免長假後測考？", ['不限', '是', '否'], horizontal=True)
            if avoid_holiday != '不限' and 'avoid_holiday_exams' in filtered_df.columns: filtered_df = filtered_df[filtered_df['avoid_holiday_exams'] == avoid_holiday]
            afternoon_tut = st.radio("設下午導修時段？", ['不限', '是', '否'], horizontal=True)
            if afternoon_tut != '不限' and 'afternoon_tutorial' in filtered_df.columns: filtered_df = filtered_df[filtered_df['afternoon_tutorial'] == afternoon_tut]
        st.markdown("---"); st.header(f"搜尋結果"); st.info(f"綜合所有條件，共找到 {len(filtered_df)} 所學校。")
        for index, school in filtered_df.iterrows():
            with st.expander(f"**{school['學校名稱']}** ({school.get('地區', 'N/A')})"):
                st.markdown("#### 🏫 學校設施詳情")
                facility_counts = (f"🏫 課室: {school.get('課室數目', 'N/A')} | 🏛️ 禮堂: {school.get('禮堂數目', 'N/A')} | 🤸 操場: {school.get('操場數目', 'N/A')} | 📚 圖書館: {school.get('圖書館數目', 'N/A')}")
                st.markdown(facility_counts)
                other_facilities = {"特別室": "特別室", "支援有特殊教育需要學生的設施": "SEN 支援設施", "其他學校設施": "其他設施"}
                for column_name, display_title in other_facilities.items():
                    detail_value = school.get(column_name, '');
                    if pd.notna(detail_value) and str(detail_value).strip() not in ['', '-']: st.write(f"**{display_title}:** {detail_value}")
                st.markdown("---"); total_teachers = school.get('全校教師總人數', 0); approved_teachers = school.get('核准編制教師職位數目
