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
        flat_keywords = []
        for item in keywords:
            if isinstance(item, list):
                flat_keywords.extend(item)
            else:
                flat_keywords.append(item)
        
        pattern = '|'.join([re.escape(keyword) for keyword in flat_keywords])
        if pattern:
            html_output = re.sub(
                pattern,
                lambda match: f'<span style="background-color: yellow;">{match.group(0)}</span>',
                html_output,
                flags=re.IGNORECASE
            )
    return html_output

# --- 核心功能函式 (處理資料) ---
@st.cache_data
def process_dataframe(df, articles_df=None, net_df=None):
    df.replace('-', '沒有', inplace=True)

    if net_df is not None and not net_df.empty:
        if '學校名稱' in net_df.columns and '地區' in net_df.columns and '校網' in net_df.columns:
            df = pd.merge(df, net_df[['學校名稱', '地區', '校網']], on='學校名稱', how='left')
        else:
            st.warning("Excel 檔案中的「校網資料」工作表缺少必要的欄位（學校名稱, 地區, 校網）。")

    if articles_df is not None and not articles_df.empty:
        if '學校名稱' in articles_df.columns and '文章標題' in articles_df.columns and '文章連結' in articles_df.columns:
            articles_df.dropna(subset=['文章標題', '文章連結'], inplace=True)
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
    
    df['full_text_search'] = df.astype(str).agg(' '.join, axis=1)

    text_columns_for_features = ['學校發展計劃', '學習和教學重點', '學校特色', '校風', '辦學宗旨', '全方位學習']
    existing_feature_columns = [col for col in text_columns_for_features if col in df.columns]
    df['features_text'] = df[existing_feature_columns].fillna('').astype(str).agg(' '.join, axis=1)
    
    percentage_cols = {
        '上學年已接受師資培訓人數百分率': '已接受師資培訓(佔全校教師人數%)',
        '上學年學士人數百分率': '學士(佔全校教師人數%)',
        '上學年碩士_博士或以上人數百分率': '碩士、博士或以上 (佔全校教師人數%)',
        '上學年特殊教育培訓人數百分率': '特殊教育培訓 (佔全校教師人數%)',
        '上學年0至4年年資人數百分率': '0-4年資 (佔全校教師人數%)',
        '上學年5至9年年資人數百分率': '5-9年資(佔全校教師人數%)',
        '上學年10年年資或以上人數百分率': '10年或以上年資 (佔全校教師人數%)'
    }
    for new_col, old_col_name in percentage_cols.items():
        if new_col in df.columns:
            s = pd.to_numeric(df[new_col].astype(str).str.replace('%', '', regex=False), errors='coerce').fillna(0)
            df[old_col_name] = s.round(1)
            
    df['p1_no_exam_assessment'] = df['小一上學期測考'].apply(lambda x: '是' if str(x).strip() == '有' else '否') if '小一上學期測考' in df.columns else '否'
    df['avoid_holiday_exams'] = df['長假期後測考'].apply(lambda x: '是' if str(x).strip() == '沒有' else '否') if '長假期後測考' in df.columns else '否'
    df['afternoon_tutorial'] = df['下午家課輔導'].apply(lambda x: '是' if str(x).strip() == '有' else '否') if '下午家課輔導' in df.columns else '否'
    df['has_pta'] = df['家長教師會'].apply(lambda x: '是' if str(x).strip() == '有' else '否') if '家長教師會' in df.columns else '否'
    
    if '學校類別1' in df.columns:
        def standardize_category(cat):
            cat_str = str(cat)
            if '官立' in cat_str: return '官立'
            if '直資' in cat_str: return '直資'
            if '資助' in cat_str: return '資助'
            if '私立' in cat_str: return '私立'
            return cat
        df['學校類別'] = df['學校類別1'].apply(standardize_category)
    else:
        df['學校類別'] = '未提供'

    has_bus = df['校車'].astype(str).str.strip() == '有' if '校車' in df.columns else pd.Series(False, index=df.index)
    has_nanny = df['保姆車'].astype(str).str.strip() == '有' if '保姆車' in df.columns else pd.Series(False, index=df.index)
    df['has_school_bus'] = '否'
    df.loc[has_bus | has_nanny, 'has_school_bus'] = '是'
    df['bus_service_text'] = '沒有'
    df.loc[has_bus & has_nanny, 'bus_service_text'] = '有校車及保姆車'
    df.loc[has_bus & ~has_nanny, 'bus_service_text'] = '有校車'
    df.loc[~has_bus & has_nanny, 'bus_service_text'] = '有保姆車'
    
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

# --- 主要應用程式邏輯 ---
try:
    # --- 修改：已換上您最新的 database.xlsx 的 Raw URL ---
    DATA_URL = "https://raw.githubusercontent.com/kingyeung625/hk-school-selector/main/database.xlsx"
    
    main_dataframe = pd.read_excel(DATA_URL, sheet_name='學校資料', engine='openpyxl')
    
    articles_dataframe = None
    try:
        articles_dataframe = pd.read_excel(DATA_URL, sheet_name='相關文章', engine='openpyxl')
    except Exception:
        st.info("提示：在 Excel 檔案中找不到名為「相關文章」的工作表。")

    net_dataframe = None
    try:
        net_dataframe = pd.read_excel(DATA_URL, sheet_name='校網資料', engine='openpyxl')
    except Exception:
        st.info("提示：在 Excel 檔案中找不到名為「校網資料」的工作表。")


    processed_df = process_dataframe(main_dataframe, articles_dataframe, net_dataframe)
    
    active_filters = []
    with st.expander("📝 按學校名稱搜尋", expanded=True):
        search_keyword = st.text_input("**輸入學校名稱關鍵字：**", key="name_search")
        if search_keyword: active_filters.append(('name', search_keyword))
    with st.expander("ℹ️ 按學校基本資料搜尋", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            if '學校類別' in processed_df.columns:
                cat_options = sorted(processed_df['學校類別'].dropna().unique())
                selected_cats = st.multiselect("學校類別", options=cat_options, key="category_select")
                if selected_cats: active_filters.append(('category', selected_cats))
            if '學生性別' in processed_df.columns:
                gender_options = sorted(processed_df['學生性別'].dropna().unique())
                selected_genders = st.multiselect("學生性別", options=gender_options, key="gender_select")
                if selected_genders: active_filters.append(('gender', selected_genders))
        with col2:
            if '宗教' in processed_df.columns:
                religion_options = sorted(processed_df['宗教'].dropna().unique())
                selected_religions = st.multiselect("宗教", options=religion_options, key="religion_select")
                if selected_religions: active_filters.append(('religion', selected_religions))
            if '教學語言' in processed_df.columns:
                lang_options = ['不限'] + sorted(processed_df['教學語言'].dropna().unique())
                selected_lang = st.selectbox("教育語言", options=lang_options, key="language_select")
                if selected_lang != '不限': active_filters.append(('language', selected_lang))
        with col3:
            if '辦學團體' in processed_df.columns:
                body_counts = processed_df['辦學團體'].value_counts()
                body_df = body_counts.reset_index()
                body_df.columns = ['辦學團體', 'count']
                body_df_sorted = body_df.sort_values(by=['count', '辦學團體'], ascending=[False, True])
                
                formatted_body_options = [ f"{row['辦學團體']} ({row['count']})" for index, row in body_df_sorted.iterrows()]
                selected_formatted_bodies = st.multiselect("辦學團體", options=formatted_body_options, key="body_select")
                
                if selected_formatted_bodies:
                    original_body_names = [item.rsplit(' (', 1)[0] for item in selected_formatted_bodies]
                    active_filters.append(('body', original_body_names))
            
            feeder_choice = st.radio("有關聯中學？", ['不限', '是', '否'], horizontal=True, key='feeder')
            if feeder_choice != '不限': active_filters.append(('feeder', feeder_choice))
            
            bus_choice = st.radio("有校車或保姆車服務？", ['不限', '是', '否'], horizontal=True, key='bus')
            if bus_choice != '不限': active_filters.append(('bus', bus_choice))
            
    with st.expander("📍 按地區及校網搜尋", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            all_districts = sorted(processed_df['地區'].dropna().unique()); selected_districts = st.multiselect("**選擇地區 (可多選)**", options=all_districts, key="district_select")
            if selected_districts: active_filters.append(('district', selected_districts))
        with col2:
            if '校網' in processed_df.columns:
                net_df = processed_df[processed_df['地區'].isin(selected_districts)] if selected_districts else processed_df
                available_nets = sorted(net_df['校網'].dropna().unique())
                selected_nets = st.multiselect("**選擇校網 (可多選)**", options=available_nets, key="net_select")
                if selected_nets: active_filters.append(('net', selected_nets))

    st.markdown('<div style="border: 2px dashed #cccccc; padding: 20px; text-align: center; margin-top: 20px; margin-bottom: 20px;">廣告空間</div>', unsafe_allow_html=True)

    with st.expander("🌟 按辦學特色搜尋", expanded=False):
        full_search_term = st.text_input("輸入任何關鍵字搜尋全校資料 (例如：奧數、面試班):", key="full_text_search")
        if full_search_term:
            active_filters.append(('full_text', full_search_term))
        st.markdown("---")
        st.markdown("**按預設標籤篩選：**")

        feature_mapping = {"【教學模式與重點】": {"自主學習及探究": ['自主學習', '探究'],"STEAM": ['STEAM', '創客'], "電子學習": ['電子學習', 'e-learning'], "閱讀": ['閱讀'], "資優教育": ['資優'], "專題研習": ['專題研習'], "跨課程學習": ['跨課程'], "兩文三語": ['兩文三語'], "英文教育": ['英文'], "家校合作": ['家校合作'], "境外交流": ['境外交流'], "藝術": ['藝術'], "體育": ['體育']},"【價值觀與品德】": {"中華文化教育": ['中華文化'], "正向、價值觀、生命教育": ['正向', '價值觀', '生命教育'], "國民教育、國安教育": ['國民', '國安'], "服務教育": ['服務'], "關愛及精神健康": ['關愛', '健康']},"【學生支援與發展】": {"全人發展": ['全人發展', '多元發展'], "生涯規劃、啟發潛能": ['生涯規劃', '潛能'], "拔尖補底、照顧差異": ['拔尖補底', '個別差異'], "融合教育": ['融合教育']}}
        col1, col2, col3 = st.columns(3); all_selected_options = []
        with col1: selected1 = st.multiselect("教學模式與重點", options=list(feature_mapping["【教學模式與重點】"].keys()), key="features1"); all_selected_options.extend(selected1)
        with col2: selected2 = st.multiselect("價值觀與品德", options=list(feature_mapping["【價值觀與品德】"].keys()), key="features2"); all_selected_options.extend(selected2)
        with col3: selected3 = st.multiselect("學生支援與發展", options=list(feature_mapping["【學生支援與發展】"].keys()), key="features3"); all_selected_options.extend(selected3)
        if all_selected_options: active_filters.append(('features', all_selected_options))
    
    with st.expander("🎓 按師資條件搜尋", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            col1_sliders = {'已接受師資培訓(佔全校教師人數%)': '師資培訓比例 (%)', '學士(佔全校教師人數%)': '學士學歷比例 (%)', '碩士、博士或以上 (佔全校教師人數%)': '碩士或以上學歷比例 (%)'}
            for col_name, slider_label in col1_sliders.items():
                if col_name in processed_df.columns:
                    min_val = st.slider(slider_label, 0, 100, 0, 5, key=col_name)
                    if min_val > 0: active_filters.append(('slider', (col_name, min_val)))
        with col2:
            col2_sliders = {'0-4年資 (佔全校教師人數%)': '0-4年資比例 (%)', '5-9年資(佔全校教師人數%)': '5-9年資比例 (%)', '10年或以上年資 (佔全校教師人數%)': '10年以上年資比例 (%)'}
            for col_name, slider_label in col2_sliders.items():
                if col_name in processed_df.columns:
                    min_val = st.slider(slider_label, 0, 100, 0, 5, key=col_name)
                    if min_val > 0: active_filters.append(('slider', (col_name, min_val)))
        with col3:
            col3_sliders = {'特殊教育培訓 (佔全校教師人數%)': '特殊教育培訓比例 (%)'}
            for col_name, slider_label in col3_sliders.items():
                if col_name in processed_df.columns:
                    min_val = st.slider(slider_label, 0, 100, 0, 5, key=col_name)
                    if min_val > 0: active_filters.append(('slider', (col_name, min_val)))

    with st.expander("📚 按課業安排搜尋", expanded=False):
        st.markdown("**評估次數**"); col1, col2 = st.columns(2)
        with col1:
            max_p1_tests = st.selectbox('小一全年最多測驗次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p1_test')
            if max_p1_tests != '任何次數': active_filters.append(('max_p1_tests', max_p1_tests))
            max_p2_6_tests = st.selectbox('小二至六全年最多測驗次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p2-6_test')
            if max_p2_6_tests != '任何次數': active_filters.append(('max_p2_6_tests', max_p2_6_tests))
        with col2:
            max_p1_exams = st.selectbox('小一全年最多考試次數', options=['任何次數', 0, 1, 2, 3], index=0, key='p1_exam')
            if max_p1_exams != '任何次數': active_filters.append(('max_p1_exams', max_p1_exams))
            max_p2_6_exams = st.selectbox('二至六年級最多考試次數', options=['任何次數', 0, 1, 2, 3, 4], index=0, key='p2-6_exam')
            if max_p2_6_exams != '任何次數': active_filters.append(('max_p2_6_exams', max_p2_6_exams))
        st.markdown("**其他安排**"); p1_no_exam = st.radio("小一上學期以多元化評估代替測考？", ['不限', '是', '否'], horizontal=True, key="p1_no_exam_radio")
        if p1_no_exam != '不限': active_filters.append(('p1_no_exam', p1_no_exam))
        avoid_holiday = st.radio("避免長假後測考？", ['不限', '是', '否'], horizontal=True, key='holiday')
        if avoid_holiday != '不限': active_filters.append(('avoid_holiday', avoid_holiday))
        afternoon_tut = st.radio("設下午導修時段？", ['不限', '是', '否'], horizontal=True, key='tutorial')
        if afternoon_tut != '不限': active_filters.append(('afternoon_tut', afternoon_tut))
    
    def reset_filters():
        keys_to_reset = [ "name_search", "category_select", "gender_select", "religion_select", "language_select", "body_select", "feeder", "bus", "district_select", "net_select", "full_text_search", "features1", "features2", "features3", "p1_test", "p2-6_test", "p1_exam", "p2-6_exam", "p1_no_exam_radio", "holiday", "tutorial"]
        slider_key_names = list(percentage_cols.values())
        keys_to_reset.extend(slider_key_names)
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.page = 0
    
    st.button("重設搜尋器", on_click=reset_filters, key="reset_button_top")
    
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
            elif filter_type == 'feeder': filtered_df = filtered_df[filtered_df['has_feeder_school'] == value]
            elif filter_type == 'bus': filtered_df = filtered_df[filtered_df['has_school_bus'] == value]
            elif filter_type == 'full_text':
                filtered_df = filtered_df[filtered_df['full_text_search'].str.contains(value, case=False, na=False)]
                all_selected_keywords_for_highlight.append(value)
            elif filter_type == 'district': filtered_df = filtered_df[filtered_df['地區'].isin(value)]
            elif filter_type == 'net': filtered_df = filtered_df[filtered_df['校網'].isin(value)]
            elif filter_type == 'features':
                for option in value:
                    search_terms = [];
                    for category in feature_mapping.values():
                        if option in category: search_terms = category[option]; all_selected_keywords_for_highlight.append(search_terms); break
                    if search_terms:
                        regex_pattern = '|'.join([re.escape(term) for term in search_terms])
                        filtered_df = filtered_df[filtered_df['features_text'].str.contains(regex_pattern, case=False, na=False, regex=True)]
            elif filter_type == 'slider':
                col_name, min_val = value; 
                if col_name in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df[col_name] >= min_val]
            elif filter_type == 'max_p1_tests': filtered_df = filtered_df[filtered_df['小一全年測驗次數'] <= int(value)]
            elif filter_type == 'max_p2_6_tests': filtered_df = filtered_df[filtered_df['小二至小六全年測驗次數'] <= int(value)]
            elif filter_type == 'max_p1_exams': filtered_df = filtered_df[filtered_df['小一全年考試次數'] <= int(value)]
            elif filter_type == 'max_p2_6_exams': filtered_df = filtered_df[filtered_df['小二至小六全年考試次數'] <= int(value)]
            elif filter_type == 'p1_no_exam': filtered_df = filtered_df[filtered_df['p1_no_exam_assessment'] == value]
            elif filter_type == 'avoid_holiday': filtered_df = filtered_df[filtered_df['avoid_holiday_exams'] == value]
            elif filter_type == 'afternoon_tut': filtered_df = filtered_df[filtered_df['afternoon_tutorial'] == value]
        
        st.video("https://www.youtube.com/watch?v=5LNrTnWvuho")
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
                                st.markdown(f'<a href="{url}" target="_blank"><img src="{image_url}" alt="{title}" style="width:100%; max-width:400px; border-radius: 8px; margin-bottom: 5px;"></a>', unsafe_allow_html=True)
                                st.markdown(f'**<a href="{url}" target="_blank" style="text-decoration: none; color: #333;">{title}</a>**', unsafe_allow_html=True)
                            else:
                                st.markdown(f"- [{title}]({url})")
                        st.markdown("---")

                    st.markdown("#### 📖 學校基本資料")
                    info_col1, info_col2 = st.columns(2)
                    with info_col1:
                        st.write(f"**學校類別:** {school.get('學校類別', '未提供')}")
                        st.write(f"**辦學團體:** {school.get('辦學團體', '未提供')}")
                        st.write(f"**創校年份:** {school.get('創校年份', '未提供')}")
                        st.write(f"**校長:** {school.get('校長姓名', '未提供')}")
                        st.write(f"**教學語言:** {school.get('教學語言', '未提供')}")
                    with info_col2:
                        st.write(f"**學生性別:** {school.get('學生性別', '未提供')}")
                        st.write(f"**宗教:** {school.get('宗教', '未提供')}")
                        st.write(f"**校網:** {school.get('校網', '未提供')}")
                        st.write(f"**校監:** {school.get('校監_校管會主席姓名', '未提供')}")
                        st.write(f"**家教會:** {school.get('has_pta', '未提供')}")

                    st.write(f"**學校佔地面積:** {school.get('學校佔地面積', '未提供')}")
                    st.write(f"**校車服務:** {school.get('bus_service_text', '沒有')}")
                    
                    feeder_schools = {"一條龍中學": school.get('一條龍中學'), "直屬中學": school.get('直屬中學'), "聯繫中學": school.get('聯繫中學')}
                    for title, value in feeder_schools.items():
                        if pd.notna(value) and str(value).strip() not in ['', '沒有']: st.write(f"**{title}:** {value}")
                    
                    st.markdown(
                        '<div style="border: 2px dashed #cccccc; padding: 15px; text-align: center; margin-top: 15px; margin-bottom: 15px;">廣告空間</div>',
                        unsafe_allow_html=True
                    )
                    
                    st.markdown("---")
                    st.markdown("#### 🏫 學校設施詳情")
                    facility_counts = (f"🏫 課室: {school.get('課室數目', 'N/A')} | 🏛️ 禮堂: {school.get('禮堂數目', 'N/A')} | 🤸 操場: {school.get('操場數目', 'N/A')} | 📚 圖書館: {school.get('圖書館數目', 'N/A')}")
                    st.markdown(facility_counts)
                    other_facilities = {"特別室": "特別室", "支援有特殊教育需要學生的設施": "支援有特殊教育需要學生的設施", "其他學校設施": "其他學校設施"}
                    for column_name, display_title in other_facilities.items():
                        detail_value = school.get(column_name, '');
                        if pd.notna(detail_value) and str(detail_value).strip() not in ['', '沒有']: st.write(f"**{display_title}:** {detail_value}")
                    
                    st.markdown("---")
                    st.markdown("#### 🧑‍🏫 師資團隊概覽")
                    approved_teachers = school.get('上學年核准編制教師職位數目')
                    total_teachers = school.get('上學年教師總人數')
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
                                fig1 = px.pie(edu_df, values='比例', names='類別', color_discrete_sequence=px.colors.sequential.Greens_r)
                                fig1.update_layout(showlegend=False, margin=dict(l=70, r=70, t=40, b=40), height=380, font=dict(size=16), uniformtext_minsize=14, uniformtext_mode='hide')
                                fig1.update_traces(textposition='inside', textinfo='percent+label', textfont_color='white'); st.plotly_chart(fig1, use_container_width=True, key=f"edu_pie_{index}")
                            else: st.text("無相關數據")
                        with pie_col2:
                            st.markdown("**年資分佈**"); exp_data = {'類別': ['0-4年', '5-9年', '10年以上'],'比例': [school.get('0-4年資 (佔全校教師人數%)', 0), school.get('5-9年資(佔全校教師人數%)', 0), school.get('10年或以上年資 (佔全校教師人數%)', 0)]}; exp_df = pd.DataFrame(exp_data)
                            if exp_df['比例'].sum() > 0:
                                fig2 = px.pie(exp_df, values='比例', names='類別', color_discrete_sequence=px.colors.sequential.Blues_r)
                                fig2.update_layout(showlegend=False, margin=dict(l=70, r=70, t=40, b=40), height=380, font=dict(size=16), uniformtext_minsize=14, uniformtext_mode='hide')
                                fig2.update_traces(textposition='inside', textinfo='percent+label', textfont_color='white'); st.plotly_chart(fig2, use_container_width=True, key=f"exp_pie_{index}")
                            else: st.text("無相關數據")
                    
                    st.markdown(
                        '<div style="border: 2px dashed #cccccc; padding: 15px; text-align: center; margin-top: 15px; margin-bottom: 15px;">廣告空間</div>',
                        unsafe_allow_html=True
                    )

                    st.markdown("---")
                    st.markdown("#### 📚 課業與評估安排")
                    homework_details = {"小一測驗/考試次數": f"{school.get('小一全年測驗次數', 'N/A')} / {school.get('小一全年考試次數', 'N/A')}", "高年級測驗/考試次數": f"{school.get('小二至小六全年測驗次數', 'N/A')} / {school.get('小二至小六全年考試次數', 'N/A')}", "小一免試評估": school.get('p1_no_exam_assessment', 'N/A'), "多元學習評估": school.get('多元學習評估', '未提供'), "避免長假後測考": school.get('avoid_holiday_exams', 'N/A'), "下午導修時段": school.get('afternoon_tutorial', 'N/A')}
                    for title, value in homework_details.items():
                        if pd.notna(value) and str(value).strip() != '': st.write(f"**{title}:** {value}")
                    
                    st.markdown("---")
                    st.markdown("#### ✨ 辦學特色與發展計劃")
                    feature_text_map = {"學校發展計劃": "學校發展計劃", "學習和教學重點": "學習和教學重點", "學校特色": "學校特色"}
                    for column_name, display_title in feature_text_map.items():
                        detail_value = school.get(column_name, '')
                        if pd.notna(detail_value) and str(detail_value).strip() not in ['', '沒有']:
                            should_expand = False
                            if all_selected_keywords_for_highlight:
                                text_to_check = str(detail_value).lower()
                                flat_keywords = []
                                for item in all_selected_keywords_for_highlight:
                                    if isinstance(item, list):
                                        flat_keywords.extend(item)
                                    else:
                                        flat_keywords.append(item)
                                if any(keyword.lower() in text_to_check for keyword in flat_keywords):
                                    should_expand = True
                            
                            with st.expander(f"**{display_title}**", expanded=should_expand):
                                formatted_content = format_and_highlight_text(detail_value, all_selected_keywords_for_highlight)
                                st.markdown(formatted_content, unsafe_allow_html=True)

                        if column_name == '學校特色': # Example of specific placement
                            st.markdown(
                                '<div style="border: 2px dashed #cccccc; padding: 15px; text-align: center; margin-top: 15px; margin-bottom: 15px;">廣告空間</div>',
                                unsafe_allow_html=True
                            )
                    
                    st.markdown(
                        '<div style="border: 2px dashed #cccccc; padding: 15px; text-align: center; margin-top: 15px; margin-bottom: 15px;">廣告空間</div>',
                        unsafe_allow_html=True
                    )

            st.markdown("---")
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                st.button("重設搜尋器", on_click=reset_filters, key="reset_button_bottom")
            
            if total_pages > 1:
                page_selection_col, next_button_col = st.columns([2,1])
                with page_selection_col:
                    page_options = [f"第 {i+1} 頁" for i in range(total_pages)]
                    current_page_label = f"第 {st.session_state.page + 1} 頁"
                    new_page_label = st.selectbox("頁數", options=page_options, index=st.session_state.page, label_visibility="collapsed")
                    if new_page_label != current_page_label:
                        st.session_state.page = page_options.index(new_page_label)
                        st.rerun()

                with next_button_col:
                     if st.session_state.page > 0:
                        st.button("⬅️ 上一頁", on_click=lambda: st.session_state.update(page=st.session_state.page - 1), key="prev_page", use_container_width=True)
                     if st.session_state.page < total_pages - 1:
                        st.button("下一頁 ➡️", on_click=lambda: st.session_state.update(page=st.session_state.page + 1), key="next_page", use_container_width=True)
except FileNotFoundError:
    st.error(f"錯誤：找不到資料檔案 '{DATA_URL}'。")
    st.info("請確認您已將正確的 Raw URL 貼入程式碼中。")
except Exception as e:
    st.error(f"處理資料時發生錯誤：{e}")
