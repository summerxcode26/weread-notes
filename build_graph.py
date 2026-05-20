#!/usr/bin/env python3
"""
Build knowledge graph from WeRead notes.
Outputs graph_data.js with window.WR_GRAPH = {nodes, links}.
"""

import json, re, math
from collections import Counter, defaultdict

# ─────────────────────────────────────────────
# Comprehensive Chinese stopword list
# ─────────────────────────────────────────────
STOP_SINGLE = set("的了是在有和就也都这那个很不一到以为他她它们我你与及于从被把让对")

STOP_WORDS = {
    # Pronouns / generic reference
    "自己","他们","我们","你们","自身","彼此","大家","所有人","每个人","每个","某个","什么","哪些",
    "这些","那些","这种","那种","这样","那样","这里","那里","这个","那个","某种","某些","各种",
    # Modal / auxiliary
    "可能","应该","必须","需要","能够","可以","将会","一定","当然","本来","也许","或许","估计",
    "未必","不一定","必然","理应","势必","不得不","只能","不能不",
    # Generic adverbs
    "非常","已经","真正","完全","仍然","还是","只是","就是","甚至","只要","似乎","有些","有点",
    "十分","相当","确实","毫无","始终","往往","通常","经常","总是","几乎","大多","大概","基本",
    "主要","一般","特别","尤其","更加","越来","越来越","反而","却是","其实","实际上","事实上",
    "不断","持续","逐渐","逐步","一直","一再","依然","依旧","至今","从来","从不","如何","任何",
    # Generic connectors
    "之间","对于","由于","因为","所以","但是","虽然","尽管","如果","那么","因此","从而","而是",
    "而且","不仅","不但","换言之","所谓","也就是","从某种","在某种","在很大",
    # Generic verbs
    "知道","发现","告诉","发生","产生","开始","希望","觉得","喜欢","感觉","认为","表示","进行",
    "通过","看到","看见","听到","想到","想起","出现","使用","利用","建立","形成","提供","实现",
    "成为","面对","理解","了解","认识","意识","注意","决定","选择","相信","感到","找到","提出",
    "来自","属于","导致","引起","促进","推动","带来","造成","影响","达到","得到","获得","具有",
    "拥有","包含","包括","涉及","表达","传达","体现","反映","代表","说明","证明","解释","描述",
    "叙述","介绍","讲述","论述","谈到","提到","写到","说到","告诉",
    # Generic adjectives
    "重要","简单","复杂","普通","正常","特殊","相同","不同","类似","具体","真实","有效","重要",
    "清楚","明显","实际","独特","本质","根本","关键","核心","基础","基本","彻底",
    # Generic / too-broad nouns
    "东西","事情","地方","意思","部分","时候","方式","时间","方面","情况","过程","结果","内容",
    "原因","目的","作用","效果","条件","方向","层面","维度","角度","阶段","背景","方法","状态",
    "状况","程度","水平","层次","深度","高度","广度","力度","速度","规模","范围","数量","质量",
    "标准","规则","原则","依据","重点","要点","难点","特点","亮点","弱点","优点","缺点","局限",
    "不足","挑战","机会","风险","困难","阻碍","世界","人生","生命","人类","时代","现在","未来",
    "能力","价值","意义","感受","体验","印象","记忆","理解","认识","判断","评价","态度","观点",
    "立场","想法","思路","思维","思考","分析","总结","归纳","演绎","推理","判断",
    # Filler / meta-text phrases
    "这本书","这篇","读者","书中","文中","文章","章节","段落","一段话","一句话","句话",
    "书里","书上","笔记","划线","想法","点评","感悟","分享","推荐","介绍","说的","写的","讲的",
    "故事","例子","例如","比如","譬如","案例","举个","比方","举例","其实","并不是","并非","不是",
    # People name fragments (common Chinese name splits)
    "蒂夫","史蒂","布斯","乔布","史蒂夫",   # Steve Jobs fragments
    "比尔","盖茨","埃隆","马斯克","贝索斯",   # other names — keep full names elsewhere
    "作者","主人公","他说","她说","我说",
}

# Meaningful single-character concepts (classical Chinese)
ALLOW_SINGLE = {"道","气","仁","礼","义","佛","禅","儒","法","易","诗","德","孝","忠","信"}

# ─────────────────────────────────────────────
# Theme taxonomy — only concrete, specific concepts
# ─────────────────────────────────────────────
THEME_MAP = {
    "health":    ["细胞","癌症","肿瘤","基因","免疫","炎症","代谢","神经","胰岛素","维生素","癌细胞",
                  "化疗","放疗","患者","医学","药物","蛋白质","线粒体","氧化应激","益生菌","抗氧化",
                  "血糖","脂肪酸","胆固醇","端粒","干细胞","表观遗传","肠道菌","免疫系统","细胞分裂",
                  "基因突变","自噬","炎性因子","胰腺","肝脏","心脏病","糖尿病","阿尔茨海默"],
    "philosophy":["哲学","意识","存在","本质","逻辑","理性","道德","伦理","自由","真理","形而上",
                  "辩证","唯物","唯心","虚无","绝对","相对","客观","主观","本体","现象","实证",
                  "演绎","归纳","命题","悖论","信仰","意志","灵魂","智慧","认识论","方法论",
                  "形而下","第一性原理","系统思维","批判性思维","还原论","整体论"],
    "yijing":    ["易经","八卦","卦象","阴阳","五行","天干","地支","乾卦","坤卦","卦辞","爻辞",
                  "象传","彖传","系辞","周易","六十四卦","太极","河图","洛书","国学","道家","儒家",
                  "庄子","老子","道德经","孔子","孟子","荀子","礼记","春秋","诗经","四书五经",
                  "天地人","阴阳五行","易学","六爻","梅花易数"],
    "history":   ["历史","朝代","皇帝","战争","帝国","文明","考古","史书","王朝","革命","民国",
                  "秦汉","唐宋","明清","封建","专制","民主","殖民","改革","工业革命","启蒙运动",
                  "汉武帝","秦始皇","唐太宗","历史观","历史规律","盛衰","兴亡","治乱"],
    "literature":["文学","诗歌","小说","散文","意象","典故","隐喻","叙事","修辞","红楼梦",
                  "西游记","金庸","阿加莎","文体","诗词","宋词","唐诗","古典","叙述者","视角",
                  "人物塑造","意境","浪漫主义","现实主义","意识流","叙事结构","悬疑","推理",
                  "克里斯蒂","波洛","马普尔","武侠","侠义"],
    "business":  ["产品","市场","商业","管理","战略","创业","用户","增长","运营","公司","团队",
                  "销售","客户","营收","利润","品牌","竞争","垄断","生态","平台","数据","流量",
                  "SaaS","商业模式","供应链","价值链","护城河","PMF","MVP","产品经理",
                  "乔布斯","苹果","华为","任正非","商业逻辑","客户成功","续费率","转化率"],
    "science":   ["量子","物理","化学","进化","基因组","宇宙","黑洞","相对论","量子力学",
                  "热力学","熵","复杂系统","混沌","涌现","网络效应","幂次定律","正态分布",
                  "实验","假设","统计","概率","算法","人工智能","机器学习","神经网络","大数据",
                  "达尔文","自然选择","物种","宇宙学","粒子物理","量子纠缠"],
    "psychology":["心理","行为","认知","情绪","动机","焦虑","抑郁","人格","压力","潜意识",
                  "认知偏差","确认偏误","损失厌恶","锚定效应","从众效应","心流","正念","冥想",
                  "自我效能","成长型思维","固定型思维","行为经济学","神经科学","社交焦虑",
                  "依附理论","原生家庭","自我认同","亲密关系","共情"],
    "life":      ["成长","幸福","情感","家庭","习惯","时间管理","自律","极简","断舍离",
                  "人际关系","沟通","领导力","执行力","创造力","专注","深度工作","心态",
                  "感恩","孤独","死亡","长寿","老龄化","价值观","人生意义","生死","生活方式",
                  "简约","精要主义","第二曲线"],
}

# Build reverse: concept → theme
CONCEPT_THEME = {}
for theme, concepts in THEME_MAP.items():
    for c in concepts:
        if c not in CONCEPT_THEME:
            CONCEPT_THEME[c] = theme


def is_valid_term(term):
    if len(term) == 1:
        return term in ALLOW_SINGLE
    if len(term) > 6:
        return False
    if term in STOP_WORDS:
        return False
    if term[0] in STOP_SINGLE or term[-1] in STOP_SINGLE:
        return False
    if not all('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in term):
        return False
    return True


def extract_terms(text):
    text = re.sub(r'[^一-鿿㐀-䶿]', '', text)
    terms = []
    for n in (2, 3, 4):
        for i in range(len(text) - n + 1):
            t = text[i:i+n]
            if is_valid_term(t):
                terms.append(t)
    return terms


def assign_theme(term, coterms):
    if term in CONCEPT_THEME:
        return CONCEPT_THEME[term]
    votes = Counter()
    for ct in coterms:
        if ct in CONCEPT_THEME:
            votes[CONCEPT_THEME[ct]] += 1
    if votes:
        return votes.most_common(1)[0][0]
    return "general"


def build_graph(notes_path, out_path, top_n=150):
    print("Loading notes...")
    with open(notes_path) as f:
        notes = json.load(f)
    total_books = len(set(n["title"] for n in notes))
    print(f"  {len(notes)} notes, {total_books} books")

    # Per-note term extraction
    print("Extracting terms...")
    note_terms = []
    for n in notes:
        combined = (n.get("text", "") + " " + n.get("thought", "")).strip()
        if not combined:
            note_terms.append([])
            continue
        terms = extract_terms(combined)
        # Add known concepts from CONCEPT_THEME (exact match)
        for concept in CONCEPT_THEME:
            if len(concept) >= 2 and concept in combined and concept not in STOP_WORDS:
                terms.append(concept)
        note_terms.append(list(set(terms)))  # deduplicate within note

    # Global counts
    print("Computing frequencies...")
    term_total = Counter()
    term_book_set = defaultdict(set)
    for i, (n, terms) in enumerate(zip(notes, note_terms)):
        book = n["title"]
        for t in terms:
            term_total[t] += 1
            term_book_set[t].add(book)

    # TF-IDF: penalize terms in >35% of books (too generic)
    max_books = int(total_books * 0.35)

    def tfidf(term):
        tf = term_total[term]
        book_freq = len(term_book_set[term])
        if book_freq > max_books:
            return 0  # too generic
        idf = math.log(total_books / (1 + book_freq))
        return tf * idf

    # Candidates: ≥3 total occurrences, ≥2 books, ≤35% of books
    candidates = [
        t for t in term_total
        if term_total[t] >= 3
        and 2 <= len(term_book_set[t]) <= max_books
    ]

    # Score
    scored = sorted(candidates, key=lambda t: tfidf(t), reverse=True)

    # Substring deduplication: remove term if it's a strict substring of a higher-ranked term
    def remove_substrings(terms_ordered):
        kept = []
        kept_set = set()
        for t in terms_ordered:
            # Check if t is a substring of any already-kept term
            if any(t in longer and t != longer for longer in kept_set):
                continue
            kept.append(t)
            kept_set.add(t)
        return kept

    scored_deduped = remove_substrings(scored)

    # Must-include from CONCEPT_THEME that pass filters
    must_include = {
        c for c in CONCEPT_THEME
        if c in term_total and term_total[c] >= 2 and c not in STOP_WORDS
        and len(term_book_set.get(c, set())) <= max_books
    }

    # Build final selection: must_include first, then top TF-IDF
    selected_set = set()
    selected = []
    for t in scored_deduped:
        if t in must_include:
            selected.append(t)
            selected_set.add(t)
    for t in scored_deduped:
        if len(selected) >= top_n:
            break
        if t not in selected_set:
            selected.append(t)
            selected_set.add(t)
    selected = selected[:top_n]
    selected_set = set(selected)   # rebuild from truncated list to keep node/edge consistent
    print(f"  Selected {len(selected)} concepts")

    # Build nodes with theme assignment
    concept_coterms = defaultdict(Counter)
    for terms in note_terms:
        in_note = [t for t in terms if t in selected_set]
        for t in in_note:
            for other in in_note:
                if other != t:
                    concept_coterms[t][other] += 1

    nodes = []
    for t in selected:
        co = list(concept_coterms[t].keys())
        theme = assign_theme(t, co)
        nodes.append({
            "id": t,
            "label": t,
            "count": term_total[t],
            "books": len(term_book_set[t]),
            "theme": theme,
        })

    # Build co-occurrence edges (within same note)
    print("Building edges...")
    edge_count = Counter()
    for terms in note_terms:
        in_note = sorted(set(t for t in terms if t in selected_set))
        for j in range(len(in_note)):
            for k in range(j + 1, len(in_note)):
                key = (in_note[j], in_note[k])
                edge_count[key] += 1

    links = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in edge_count.items() if w >= 2
    ]
    links.sort(key=lambda x: -x["weight"])
    links = links[:500]
    print(f"  {len(links)} edges")

    theme_labels = {
        "health": "健康/医学", "philosophy": "哲学/思想", "yijing": "易经/国学",
        "history": "历史", "literature": "文学", "business": "商业/管理",
        "science": "科学", "psychology": "心理学", "life": "生活/成长", "general": "通用",
    }

    graph = {"nodes": nodes, "links": links, "theme_labels": theme_labels}
    js = ("// Knowledge graph — auto-generated\n"
          "window.WR_GRAPH=" + json.dumps(graph, ensure_ascii=False, separators=(',', ':')) + ";\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(js)

    size = len(js.encode()) // 1024
    print(f"  Written: {out_path} ({size} KB)")

    print("\nTop 40 concepts:")
    for t in scored_deduped[:40]:
        if t in selected_set:
            node = next(n for n in nodes if n["id"] == t)
            print(f"  {t:8s}  cnt={term_total[t]:4d}  books={len(term_book_set[t]):3d}  theme={node['theme']}")

    return graph


if __name__ == "__main__":
    build_graph(
        notes_path="/tmp/all_notes_processed.json",
        out_path="/Users/S/vibe/weread-notes/graph_data.js",
    )
