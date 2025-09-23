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
st.write("請上傳包含學校資料的檔案。建議使用有「學校資料」和「相關文章」兩個工作表的 Excel 檔案。")

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
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        og_image_tag = soup.find('meta', property='og:image')
        
        if og_image_tag and og_image_tag.get('content'):
            return og_image_tag['content']
            
    except requests.RequestException:
        return None
    return None

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
def process_dataframe(df, articles_df=None):
    df.replace('-', '沒有', inplace=True)

    if articles_df is not None and not articles_df.empty:
        if '學校名稱' in articles_df.columns and '文章標題' in articles_df.columns and '文章連結' in articles_df.columns:
            # --- 修正開始：先過濾掉標題或連結為空的無效文章資料 ---
            articles_df.dropna(subset=['文章標題', '文章連結'], inplace=True)
            # --- 修正結束 ---

            articles_grouped = articles_df.groupby('學校名稱').apply(
                lambda x: list(zip(x['文章標題'], x['文章連結']))
            ).reset_index(name='articles')
            df = pd.merge(df, articles_grouped, on='學校名稱', how='left')
            df['articles'] = df['articles'].apply(lambda x: x if isinstance(x, list) else [])
        else:
            st.warning("Excel 檔案中的「相關文章」工作表缺少必要的欄位（學校名稱, 文章標題, 文章連結），將忽略相關文章。")
            df['articles'] = [[] for _ in range(len(df))]
    else:
        df['articles'] = [[] for _ in range(len(df))]

    # (其餘資料處理邏輯不變)
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
    
    teacher_count_cols = ['核准編制教師職位數目', '全校教師總人數']
    for col in teacher_count_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    exam_count_cols = [
        '一年級全年全科測驗次數', '一年級全年全科考試次數',
        '二至六年級全年全科測驗次數', '二至六年級全年全科考試次數'
    ]
    for col in exam_count_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            
    yes_no_cols = {
        '小一上學期以多元化的進展性評估代替測驗及考試': 'p1_no_exam_assessment',
        '避免緊接在長假期後安排測考，讓學生在假期有充分的休息': 'avoid_holiday_exams',
        '按校情靈活編排時間表，盡量在下午安排導修時段，讓學生能在教師指導下完成部分家課': 'afternoon_tutorial',
        '家教會': 'has_pta'
    }
    for col, new_name in yes_no_cols.items():
        if col in df.columns:
            df[new_name] = df[col].apply(lambda x: '是' if str(x).strip().lower() in ['有', 'yes'] else '否')
    
    bus_series = df['校車服務'].fillna('沒有').astype(str) if '校車服務' in df.columns else pd.Series('沒有', index=df.index)
    has_bus_data = bus_series.str.strip().isin(['', '沒有']) == False
    df['has_school_bus'] = '否'
    df.loc[has_bus_data, 'has_school_bus'] = '是'
    df['bus_service_text'] = '沒有'
    cond_both = bus_series.str.contains("校車") & bus_series.str.contains("保姆車")
    cond_bus_only = bus_series.str.contains("校車") & ~bus_series.str.contains("保姆車")
    cond_nanny_only = ~bus_series.str.contains("校車") & bus_series.str.contains("保姆車")
    df.loc[cond_both, 'bus_service_text'] = '有校車及保姆車'
    df.loc[cond_bus_only, 'bus_service_text'] = '有校車'
    df.loc[cond_nanny_only, 'bus_service_text'] = '有保姆車'

    df['fees_text'] = '沒有'
    df['has_fees'] = '否'
    if '學費' in df.columns:
        mask_fee = df['學費'].notna() & (df['學費'].astype(str).str.strip() != '') & (df['學費'].astype(str).str.strip() != '沒有')
        df.loc[mask_fee, 'fees_text'] = "學費: " + df['學費'].astype(str)
        df.loc[mask_fee, 'has_fees'] = '是'
    if '堂費' in df.columns:
        mask_sub = df['堂費'].notna() & (df['堂費'].astype(str).str.strip() != '') & (df['堂費'].astype(str).str.strip() != '沒有')
        mask_both = (df['has_fees'] == '是') & mask_sub
        df.loc[mask_both, 'fees_text'] += ' | ' + "堂費: " + df['堂費'].astype(str)
        mask_sub_only = (df['has_fees'] == '否') & mask_sub
        df.loc[mask_sub_only, 'fees_text'] = "堂費: " + df['堂費'].astype(str)
        df.loc[mask_sub, 'has_fees'] = '是'

    feeder_cols = ['一條龍中學', '直屬中學', '聯繫中學']
    existing_feeder_cols = [col for col in feeder_cols if col in df.columns]
    if existing_feeder_cols:
         df['has_feeder_school'] = df[existing_feeder_cols].apply(
            lambda row: '是' if any(pd.notna(val) and str(val).strip() not in ['', '沒有'] for val in row) else '否',
            axis=1
        )
    else:
        df['has_feeder_school'] = '否'
    return df

# --- 檔案上傳器 ---
uploaded_file = st.file_uploader("**請上傳您的學校資料檔案 (Excel 或 CSV)**", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        main_dataframe = None
        articles_dataframe = None
        if uploaded_file.name.endswith('.csv'):
            main_dataframe = pd.read_csv(uploaded_file, engine='python')
            st.info("您上傳的是 CSV 檔案，將只讀取學校資料。")
        else:
            try:
                main_dataframe = pd.read_excel(uploaded_file, sheet_name='學校資料', engine='openpyxl')
                articles_dataframe = pd.read_excel(uploaded_file, sheet_name='相關文章', engine='openpyxl')
            except Exception as e:
                st.error(f"讀取 Excel 檔案失敗：{e}")
                st.warning("請確認您的 Excel 檔案包含名為「學校資料」和「相關文章」的工作表。")
                main_dataframe = None

        if main_dataframe is not None:
            processed_df = process_dataframe(main_dataframe, articles_dataframe)
            st.success(f'成功讀取 {len(processed_df)} 筆學校資料！')
            
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
                    if '教學語言' in processed_df.columns:
                        lang_options = ['不限'] + sorted(processed_df['教學語言'].dropna().unique())
                        selected_lang = st.selectbox("教育語言", options=lang_options)
                        if selected_lang != '不限': active_filters.append(('language', selected_lang))
                with col2:
                    if '辦學團體' in processed_df.columns:
                        body_counts = processed_df['辦學團體'].value_counts()
                        body_options = sorted(body_counts[body_counts >= 2].index)
                        selected_bodies = st.multiselect("辦學團體 (只顯示多於一間的團體)", options=body_options)
                        if selected_bodies: active_filters.append(('body', selected_bodies))
                    fee_choice = st.radio("學費或堂費", ['不限', '有', '沒有'], horizontal=True, key='fees')
                    if fee_choice == '有': active_filters.append(('fees', '是'))
                    elif fee_choice == '沒有': active_filters.append(('fees', '否'))
                    feeder_choice = st.radio("有關聯中學？", ['不限', '是', '否'], horizontal=True, key='feeder')
                    if feeder_choice != '不限': active_filters.append(('feeder', feeder_choice))
                    bus_choice = st.radio("有校車或保姆車服務？", ['不限', '是', '否'], horizontal=True, key='bus')
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
                    if col_name in processed_df.columns:
                        min_val = st.slider(slider_label, 0, 100, 0, 5, key=col_name)
                        if min_val > 0: active_filters.append(('slider', (col_name, min_val)))
            with st.expander("📚 按課業安排搜尋", expanded=False):
                st.markdown("**評估次數**"); col1, col2 = st.columns(2)
                with col1:
                    max_p1_tests = st.selectbox('小一全年最多測驗次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p1_test')
                    if max_p1_tests != '任何次數': active_filters.append(('max_p1_tests', max_p1_tests))
                    max_p2_6_tests = st.selectbox('二至六年級最多測驗次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p2-6_test')
                    if max_p2_6_tests != '任何次數': active_filters.append(('max_p2_6_tests', max_p2_6_tests))
                with col2:
                    max_p1_exams = st.selectbox('小一全年最多考試次數', options=['任何次數', 0, 1, 2, 3], index=0, key='p1_exam')
                    if max_p1_exams != '任何次數': active_filters.append(('max_p1_exams', max_p1_exams))
                    max_p2_6_exams = st.selectbox('二至六年級最多考試次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p2-6_exam')
                    if max_p2_6_exams != '任何次數': active_filters.append(('max_p2_6_exams', max_p2_6_exams))
                st.markdown("**其他安排**"); p1_no_exam = st.radio("小一上學期以多元化評估代替測考？", ['不限', '是', '否'], horizontal=True)
                if p1_no_exam != '不限': active_filters.append(('p1_no_exam', p1_no_exam))
                avoid_holiday = st.radio("避免長假後測考？", ['不限', '是', '否'], horizontal=True, key='holiday')
                if avoid_holiday != '不限': active_filters.append(('avoid_holiday', avoid_holiday))
                afternoon_tut = st.radio("設下午導修時段？", ['不限', '是', '否'], horizontal=True, key='tutorial')
                if afternoon_tut != '不限': active_filters.append(('afternoon_tut', afternoon_tut))
            
            if active_filters != st.session_state.get('active_filters_cache', None):
                st.session_state.page = 0
                st.session_state.active_filters_cache = active_filters

            st.markdown("---"); st.header(f"搜尋結果")
            if not active_filters:
                st.info("☝️ 請使用上方的篩選器開始尋找學校。")
            else:
                filtered_df = processed_df.copy()
                all_selected_keywords_for_highlight = []
                for filter_type, value in active_filters:
                    if filter_type == 'name': filtered_df = filtered_df[filtered_df['學校名稱'].str.contains(value, case=False, na=False)]
                    elif filter_type == 'category': filtered_df = filtered_df[filtered_df['學校類別'].isin(value)]
                    elif filter_type == 'gender': filtered_df = filtered_df[filtered_df['學生性別'].isin(value)]
                    elif filter_type == 'religion': filtered_df = filtered_df[filtered_df['宗教'].isin(value)]
                    elif filter_type == 'language': filtered_df = filtered_df[filtered_df['教學語言'] == value]
                    elif filter_type == 'body': filtered_df = filtered_df[filtered_df['辦學團體'].isin(value)]
                    elif filter_type == 'fees': filtered_df = filtered_df[filtered_df['has_fees'] == value]
                    elif filter_type == 'feeder': filtered_df = filtered_df[filtered_df['has_feeder_school'] == value]
                    elif filter_type == 'bus': filtered_df = filtered_df[filtered_df['has_school_bus'] == value]
                    elif filter_type == 'district': filtered_df = filtered_df[filtered_df['地區'].isin(value)]
                    elif filter_type == 'net': filtered_df = filtered_df[filtered_df['校網'].isin(value)]
                    elif filter_type == 'features':
                        for option in value:
                            search_terms = [];
                            for category in feature_mapping.values():
                                if option in category: search_terms = category[option]; all_selected_keywords_for_highlight.extend(search_terms); break
                            if search_terms:
                                regex_pattern = '|'.join([re.escape(term) for term in search_terms])
                                filtered_df = filtered_df[filtered_df['features_text'].str.contains(regex_pattern, case=False, na=False, regex=True)]
                    elif filter_type == 'slider':
                        col_name, min_val = value; filtered_df = filtered_df[filtered_df[col_name] >= min_val]
                    elif filter_type == 'max_p1_tests': filtered_df = filtered_df[filtered_df['一年級全年全科測驗次數'] <= int(value)]
                    elif filter_type == 'max_p2_6_tests': filtered_df = filtered_df[filtered_df['二至六年級全年全科測驗次數'] <= int(value)]
                    elif filter_type == 'max_p1_exams': filtered_df = filtered_df[filtered_df['一年級全年全科考試次數'] <= int(value)]
                    elif filter_type == 'max_p2_6_exams': filtered_df = filtered_df[filtered_df['二至六年級全年全科考試次數'] <= int(value)]
                    elif filter_type == 'p1_no_exam': filtered_df = filtered_df[filtered_df['p1_no_exam_assessment'] == value]
                    elif filter_type == 'avoid_holiday': filtered_df = filtered_df[filtered_df['avoid_holiday_exams'] == value]
                    elif filter_type == 'afternoon_tut': filtered_df = filtered_df[filtered_df['afternoon_tutorial'] == value]
                
                st.info(f"綜合所有條件，共找到 {len(filtered_df)} 所學校。")
                
                if not filtered_df.empty:
                    ITEMS_PER_PAGE = 10
                    total_items = len(filtered_df)
                    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
                    st.session_state.page = max(0, min(st.session_state.page, total_pages - 1))
                    
                    start_idx = st.session_state.page * ITEMS_PER_PAGE
                    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
                    
                    page_df = filtered_df.iloc[start_idx:end_idx]
                    
                    for index, school in page_df.iterrows():
                        with st.expander(f"**{school.get('學校名稱', 'N/A')}** ({school.get('地區', 'N/A')})"):
                            articles = school.get('articles', [])
                            if articles:
                                st.markdown("#### 📖 相關報導")
                                for title, url in articles:
                                    image_url = get_article_metadata(url)
                                    if image_url:
                                        st.markdown(
                                            f'<a href="{url}" target="_blank"><img src="{image_url}" alt="{title}" style="width:100%; max-width:400px; border-radius: 8px; margin-bottom: 5px;"></a>', 
                                            unsafe_allow_html=True
                                        )
                                        st.markdown(f'**<a href="{url}" target="_blank" style="text-decoration: none; color: #333;">{title}</a>**', unsafe_allow_html=True)
                                    else:
                                        st.markdown(f"- [{title}]({url})")
                                st.markdown("---")

                            st.markdown("#### 📖 學校基本資料")
                            info_col1, info_col2 = st.columns(2)
                            with info_col1:
                                st.write(f"**學校類別:** {school.get('學校類別', '未提供')}"); st.write(f"**辦學團體:** {school.get('辦學團體', '未提供')}"); st.write(f"**創校年份:** {school.get('創校年份', '未提供')}"); st.write(f"**校長:** {school.get('校長_', '未提供')}"); st.write(f"**教學語言:** {school.get('教學語言', '未提供')}")
                            with info_col2:
                                st.write(f"**學生性別:** {school.get('學生性別', '未提供')}"); st.write(f"**宗教:** {school.get('宗教', '未提供')}"); st.write(f"**學校佔地面積:** {school.get('學校佔地面積', '未提供')}"); st.write(f"**校監:** {school.get('校監／學校管理委員會主席', '未提供')}"); st.write(f"**家教會:** {school.get('has_pta', '未提供')}")
                            
                            st.write(f"**學費/堂費:** {school.get('fees_text', '沒有')}")
                            st.write(f"**校車服務:** {school.get('bus_service_text', '沒有')}")
                            
                            feeder_schools = {"一條龍中學": school.get('一條龍中學'), "直屬中學": school.get('直屬中學'), "聯繫中學": school.get('聯繫中學')}
                            for title, value in feeder_schools.items():
                                if pd.notna(value) and str(value).strip() not in ['', '沒有']: st.write(f"**{title}:** {value}")
                            
                            st.markdown("---")
                            st.markdown("#### 🏫 學校設施詳情")
                            facility_counts = (f"🏫 課室: {school.get('課室數目', 'N/A')} | 🏛️ 禮堂: {school.get('禮堂數目', 'N/A')} | 🤸 操場: {school.get('操場數目', 'N/A')} | 📚 圖書館: {school.get('圖書館數目', 'N/A')}")
                            st.markdown(facility_counts)
                            other_facilities = {"特別室": "特別室", "支援有特殊教育需要學生的設施": "SEN 支援設施", "其他學校設施": "其他學校設施"}
                            for column_name, display_title in other_facilities.items():
                                detail_value = school.get(column_name, '');
                                if pd.notna(detail_value) and str(detail_value).strip() not in ['', '沒有']: st.write(f"**{display_title}:** {detail_value}")
                            
                            st.markdown("---")
                            st.markdown("#### 🧑‍🏫 師資團隊概覽")
                            approved_teachers = school.get('核准編制教師職位數目')
                            total_teachers = school.get('全校教師總人數')
                            col1, col2 = st.columns(2)
                            with col1:
                                if pd.isna(approved_teachers):
                                    st.metric("核准編制教師職位", "沒有資料")
                                else:
                                    st.metric("核准編制教師職位", f"{int(approved_teachers)} 人")
                            with col2:
                                if pd.isna(total_teachers):
                                    st.metric("全校教師總人數", "沒有資料")
                                else:
                                    if not pd.isna(approved_teachers):
                                        diff = total_teachers - approved_teachers
                                        if diff >= 0:
                                            st.metric("全校教師總人數", f"{int(total_teachers)} 人", f"+{int(diff)}", delta_color="normal")
                                        else:
                                            st.metric("全校教師總人數", f"{int(total_teachers)} 人", f"{int(diff)}", delta_color="inverse")
                                    else:
                                        st.metric("全校教師總人數", f"{int(total_teachers)} 人")
                            if st.button("📊 顯示師資比例圖表", key=f"chart_btn_{index}"):
                                st.markdown("#### 📊 師資比例分佈圖"); pie_col1, pie_col2 = st.columns(2)
                                with pie_col1:
                                    st.markdown("**學歷分佈**"); edu_data = {'類別': ['學士', '碩士或以上'],'比例': [school.get('學士(佔全校教師人數%)', 0), school.get('碩士、博士或以上 (佔全校教師人數%)', 0)]}; edu_df = pd.DataFrame(edu_data)
                                    if edu_df['比例'].sum() > 0:
                                        fig1 = px.pie(edu_df, values='比例', names='類別', color_discrete_sequence=px.colors.sequential.Greens_r);
                                        fig1.update_layout(showlegend=False, margin=dict(l=10, r=10, t=30, b=10), height=300, font=dict(size=14))
                                        fig1.update_traces(textposition='outside', textinfo='percent+label'); st.plotly_chart(fig1, use_container_width=True, key=f"edu_pie_{index}")
                                    else: st.text("無相關數據")
                                with pie_col2:
                                    st.markdown("**年資分佈**"); exp_data = {'類別': ['0-4年', '5-9年', '10年以上'],'比例': [school.get('0-4年資 (佔全校教師人數%)', 0), school.get('5-9年資(佔全校教師人數%)', 0), school.get('10年或以上年資 (佔全校教師人數%)', 0)]}; exp_df = pd.DataFrame(exp_data)
                                    if exp_df['比例'].sum() > 0:
                                        fig2 = px.pie(exp_df, values='比例', names='類別', color_discrete_sequence=px.colors.sequential.Blues_r);
                                        fig2.update_layout(showlegend=False, margin=dict(l=10, r=10, t=30, b=10), height=300, font=dict(size=14))
                                        fig2.update_traces(textposition='outside', textinfo='percent+label'); st.plotly_chart(fig2, use_container_width=True, key=f"exp_pie_{index}")
                                    else: st.text("無相關數據")
                            st.markdown("---")
                            st.markdown("#### 📚 課業與評估安排")
                            homework_details = {"小一測驗/考試次數": f"{school.get('一年級全年全科測驗次數', 'N/A')} / {school.get('一年級全年全科考試次數', 'N/A')}", "高年級測驗/考試次數": f"{school.get('二至六年級全年全科測驗次數', 'N/A')} / {school.get('二至六年級全年全科考試次數', 'N/A')}", "小一免試評估": school.get('p1_no_exam_assessment', 'N/A'), "多元學習評估": school.get('多元學習評估', '未提供'), "避免長假後測考": school.get('avoid_holiday_exams', 'N/A'), "下午導修時段": school.get('afternoon_tutorial', 'N/A')}
                            for title, value in homework_details.items():
                                if pd.notna(value) and str(value).strip() != '': st.write(f"**{title}:** {value}")
                            
                            st.markdown("---")
                            st.markdown("#### ✨ 辦學特色與發展計劃")
                            feature_text_map = {
                                "學校關注事項": "學校關注事項", "學習和教學策略": "學習和教學策略", "小學教育課程更新重點的發展": "課程更新重點", 
                                "共通能力的培養": "共通能力培養", "正確價值觀、態度和行為的培養": "價值觀培養", "全校參與照顧學生的多樣性": "照顧學生多樣性",
                                "全校參與模式融合教育": "融合教育模式", "非華語學生的教育支援": "非華語學生支援", "課程剪裁及調適措施": "課程剪裁調適",
                                "家校合作": "家校合作", "校風": "校風", "學校發展計劃": "學校發展計劃", "教師專業培訓及發展": "教師專業發展", 
                                "其他未來發展": "其他未來發展"
                            }
                            for column_name, display_title in feature_text_map.items():
                                detail_value = school.get(column_name, '')
                                if pd.notna(detail_value) and str(detail_value).strip() not in ['', '沒有']:
                                    
                                    should_expand = False
                                    if all_selected_keywords_for_highlight:
                                        text_to_check = str(detail_value).lower()
                                        if any(keyword.lower() in text_to_check for keyword in all_selected_keywords_for_highlight):
                                            should_expand = True
                                    
                                    with st.expander(f"**{display_title}**", expanded=should_expand):
                                        formatted_content = format_and_highlight_text(detail_value, all_selected_keywords_for_highlight)
                                        st.markdown(formatted_content, unsafe_allow_html=True)

                    st.markdown("---")
                    col1, col2, col3 = st.columns([2, 3, 2])
                    if total_pages > 1:
                        with col1:
                            if st.session_state.page > 0:
                                if st.button("⬅️ 上一頁"):
                                    st.session_state.page -= 1
                                    st.rerun()
                        with col2:
                            st.write(f"頁數: {st.session_state.page + 1} / {total_pages}")
                        with col3:
                            if st.session_state.page < total_pages - 1:
                                if st.button("下一頁 ➡️"):
                                    st.session_state.page += 1
                                    st.rerun()

    except Exception as e:
        st.error(f"檔案處理失敗：{e}")

else:
    st.info("請先上傳您的資料檔案。建議使用包含「學校資料」和「相關文章」兩個工作表的 Excel 檔案。")
