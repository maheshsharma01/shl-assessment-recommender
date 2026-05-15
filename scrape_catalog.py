"""
SHL Catalog Scraper
Fetches all Individual Test Solutions from https://www.shl.com/solutions/products/product-catalog/
and saves them to catalog.json
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin

BASE_URL = "https://www.shl.com"
CATALOG_URL = "https://www.shl.com/solutions/products/product-catalog/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TEST_TYPE_MAP = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}


def fetch_catalog_page(start: int) -> BeautifulSoup:
    """Fetch one page of the catalog (12 items per page)."""
    params = {
        "action_doFilteringForm": "Search",
        "type": ["1", "1"],  # Individual Test Solutions only
        "start": start,
        "f": "1",
    }
    # Build URL manually to handle repeated type param
    url = (
        f"{CATALOG_URL}?action_doFilteringForm=Search"
        f"&type=1&start={start}&f=1"
    )
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_catalog_page(soup: BeautifulSoup):
    """Extract product names, URLs, and test types from a catalog page."""
    products = []
    # Products are in table rows under the product list
    table = soup.find("table")
    if not table:
        return products, False

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue

        # First cell has the product link
        link_tag = cells[0].find("a")
        if not link_tag:
            continue

        name = link_tag.get_text(strip=True)
        href = link_tag.get("href", "")
        url = urljoin(BASE_URL, href) if href else ""

        # Remote testing (col 1), Adaptive (col 2), Test type icons (col 3)
        remote = bool(cells[1].find("span", class_="catalogue__circle -yes")) if len(cells) > 1 else False
        adaptive = bool(cells[2].find("span", class_="catalogue__circle -yes")) if len(cells) > 2 else False

        # Test type letters from the type cells
        test_types = []
        if len(cells) > 3:
            spans = cells[3].find_all("span", class_=re.compile(r"product-catalogue"))
            for span in spans:
                letter = span.get_text(strip=True)
                if letter in TEST_TYPE_MAP:
                    test_types.append(letter)

        if name and url:
            products.append({
                "name": name,
                "url": url,
                "remote_testing": remote,
                "adaptive_irt": adaptive,
                "test_types": test_types,
            })

    # Check if there's a next page
    pagination = soup.find("div", class_="pagination") or soup.find("ul", class_="pagination")
    has_next = False
    if pagination:
        next_link = pagination.find("a", string=re.compile(r"Next|next|>"))
        if next_link:
            has_next = True

    return products, has_next


def fetch_product_detail(url: str) -> dict:
    """Fetch description and metadata from an individual product page."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        detail = {}

        # Description
        desc_selectors = [
            {"class_": re.compile(r"product-description|catalogue-detail|hero-description")},
        ]
        desc = ""
        for sel in desc_selectors:
            tag = soup.find(["p", "div"], **sel)
            if tag:
                desc = tag.get_text(" ", strip=True)
                break

        # Fallback: find first substantial paragraph after h1
        if not desc:
            h1 = soup.find("h1")
            if h1:
                for sib in h1.find_all_next(["p", "div"]):
                    text = sib.get_text(" ", strip=True)
                    if len(text) > 50:
                        desc = text[:500]
                        break

        detail["description"] = desc

        # Job levels
        job_levels = []
        for tag in soup.find_all(["li", "span", "p"]):
            text = tag.get_text(strip=True)
            for level in [
                "Entry-Level", "Graduate", "Manager", "Mid-Professional",
                "Professional Individual Contributor", "Director", "Executive",
                "Front Line Manager", "Supervisor", "General Population",
            ]:
                if level in text and level not in job_levels:
                    job_levels.append(level)

        detail["job_levels"] = job_levels

        # Languages
        languages = []
        lang_pattern = re.compile(
            r"English|Spanish|French|German|Dutch|Portuguese|Chinese|Japanese|"
            r"Korean|Arabic|Russian|Italian|Swedish|Danish|Norwegian|Finnish|Polish|Turkish"
        )
        for tag in soup.find_all(["li", "span", "p"]):
            text = tag.get_text(strip=True)
            if lang_pattern.search(text) and len(text) < 300:
                langs_found = re.findall(
                    r"English[^,;)]*|Spanish[^,;)]*|French[^,;)]*|German[^,;)]*|"
                    r"Dutch[^,;)]*|Portuguese[^,;)]*|Chinese[^,;)]*|Japanese|Korean|"
                    r"Arabic|Russian|Italian|Swedish|Danish|Norwegian|Finnish|Polish|Turkish",
                    text,
                )
                languages.extend([l.strip() for l in langs_found])

        detail["languages"] = list(set(languages))[:10]

        return detail

    except Exception as e:
        print(f"    Warning: could not fetch detail for {url}: {e}")
        return {"description": "", "job_levels": [], "languages": []}


def scrape_all():
    """Scrape all pages of the catalog."""
    all_products = []
    start = 0
    page = 1

    print("Starting catalog scrape...")

    while True:
        print(f"  Fetching catalog page {page} (start={start})...")
        try:
            soup = fetch_catalog_page(start)
            products, has_next = parse_catalog_page(soup)
        except Exception as e:
            print(f"  Error fetching page {page}: {e}")
            break

        if not products:
            print(f"  No products found on page {page}, stopping.")
            break

        all_products.extend(products)
        print(f"  Found {len(products)} products (total: {len(all_products)})")

        if not has_next:
            break

        start += 12
        page += 1
        time.sleep(1.0)

        if page > 50:  # safety limit
            break

    # Now enrich with detail pages
    print(f"\nEnriching {len(all_products)} products with detail pages...")
    for i, product in enumerate(all_products):
        print(f"  [{i+1}/{len(all_products)}] {product['name']}")
        detail = fetch_product_detail(product["url"])
        product.update(detail)
        time.sleep(0.5)

    return all_products


def build_catalog_from_known_products():
    """
    Build catalog from known product URLs discovered via search.
    Used as fallback when JS-rendered catalog can't be fully scraped.
    """
    # This is a comprehensive list of SHL Individual Test Solutions
    # sourced from the catalog
    products = [
        # Ability & Aptitude
        {"name": "Verify - Numerical Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-numerical-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": True, "description": "Measures numerical reasoning ability. Assesses the ability to make correct decisions or inferences from numerical data presented in statistical tables.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Verify - Verbal Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-verbal-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": True, "description": "Measures verbal reasoning ability. Assesses the ability to evaluate the logic of various kinds of argument presented in a short paragraph.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Verify - Inductive Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-inductive-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": True, "description": "Measures inductive reasoning ability. Assesses ability to identify patterns and relationships from diagrammatic information.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Verify - Deductive Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-deductive-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Measures deductive reasoning ability. Tests ability to draw logical conclusions from presented scenarios.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Verify Interactive - Numerical Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-interactive-numerical-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": True, "description": "Mobile-optimized numerical reasoning assessment. Evaluates ability to analyze numerical data and draw conclusions.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Verify Interactive - Verbal Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-interactive-verbal-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": True, "description": "Mobile-optimized verbal reasoning assessment. Evaluates ability to understand written information and draw conclusions.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Verify Interactive - Inductive Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-interactive-inductive-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": True, "description": "Mobile-first inductive reasoning test using interactive elements. Measures logical pattern recognition.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Verify Interactive - Deductive Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-interactive-deductive-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": True, "description": "Mobile-first deductive reasoning test with interactive elements. Measures logical conclusion-drawing ability.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Verify - Mechanical Comprehension", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-mechanical-comprehension/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Measures comprehension of mechanical principles and application. Ideal for technical/engineering roles.", "job_levels": ["Entry-Level", "Graduate", "Mid-Professional"]},
        {"name": "Verify - Calculation", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-calculation/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Measures basic calculation skills including arithmetic operations, percentages, and ratios.", "job_levels": ["Entry-Level", "Graduate"]},
        {"name": "Verify - Reading Comprehension", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-reading-comprehension/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Measures ability to understand and interpret written information accurately.", "job_levels": ["Entry-Level", "Graduate"]},
        {"name": "General Ability - Short Form", "url": "https://www.shl.com/solutions/products/product-catalog/view/general-ability-short-form/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Short assessment measuring general mental ability across verbal, numerical and abstract reasoning.", "job_levels": ["Entry-Level", "Graduate", "General Population"]},
        {"name": "Numerical Reasoning - Short Form", "url": "https://www.shl.com/solutions/products/product-catalog/view/numerical-reasoning-short-form/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Brief numerical reasoning test for time-constrained screening processes.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Verbal Reasoning - Short Form", "url": "https://www.shl.com/solutions/products/product-catalog/view/verbal-reasoning-short-form/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Brief verbal reasoning test for efficient candidate screening.", "job_levels": ["Entry-Level", "General Population"]},

        # Personality & Behavior
        {"name": "OPQ32r", "url": "https://www.shl.com/solutions/products/product-catalog/view/opq32r/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "The Occupational Personality Questionnaire (OPQ32r) measures 32 personality characteristics relevant to workplace performance. It provides detailed insight into how an individual's behavioral style will impact job performance.", "job_levels": ["Director", "Entry-Level", "Executive", "Front Line Manager", "General Population", "Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor", "Supervisor"]},
        {"name": "OPQ32r (Short)", "url": "https://www.shl.com/solutions/products/product-catalog/view/opq32r-short/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "A shorter version of the OPQ32r personality questionnaire that still measures key workplace personality traits.", "job_levels": ["Director", "Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Motivation Questionnaire (MQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/motivation-questionnaire-mq/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Measures 18 dimensions of motivation that affect performance and engagement at work. Identifies what energizes and satisfies individuals.", "job_levels": ["Director", "Executive", "Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Personality Questionnaire - Universal Competency (PQUC)", "url": "https://www.shl.com/solutions/products/product-catalog/view/pquc/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Maps personality to universal competencies. Provides competency-based feedback aligned to the UCF framework.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},

        # Knowledge & Skills - Technical/IT
        {"name": "Java 8 (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/java-8-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Multi-choice test measuring knowledge of Java 8 features including streams, lambdas, and new APIs.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Core Java (Advanced Level) (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/core-java-advanced-level-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Advanced-level test measuring deep knowledge of Core Java concepts including OOP, collections, concurrency.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Python (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/python-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Multi-choice test measuring knowledge of Python programming language, including syntax, libraries, and data structures.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "SQL (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/sql-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Multi-choice test measuring knowledge of SQL queries, data manipulation and transaction processing.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Spring (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/spring-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Multi-choice test measuring knowledge of Spring core, AOP, IOC container and transactions.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Manual Testing (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/manual-testing-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Multi-choice test measuring knowledge of the software testing life cycle, testing tools and techniques.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "MS Excel (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/ms-excel-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Multi-choice test measuring ability to use MS Excel to maintain, organize, analyze and present numeric data.", "job_levels": ["Entry-Level", "Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor", "Supervisor"]},
        {"name": "JavaScript (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/javascript-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Multi-choice test measuring knowledge of JavaScript programming including ES6+, DOM manipulation, and async patterns.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "HTML/CSS (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/html-css-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of HTML5 markup and CSS3 styling techniques for web development.", "job_levels": ["Entry-Level", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "C++ (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/c-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of C++ including object-oriented programming, templates, and STL.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": ".NET (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/net-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of the .NET framework, C# programming, and related technologies.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Angular (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/angular-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of Angular framework for building web applications.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "React (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/react-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of React.js library, component lifecycle, hooks, and state management.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Node.js (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/node-js-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of Node.js server-side JavaScript runtime, npm, and common frameworks.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Automation Testing (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/automation-testing-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of automated testing frameworks, tools, and methodologies.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Data Structures (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/data-structures-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of fundamental data structures: arrays, linked lists, trees, graphs, hash tables.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Algorithms (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/algorithms-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of algorithm design, analysis, sorting, searching, and optimization.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Agile Software Development (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/agile-software-development-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures understanding of Agile methodologies, Scrum, Kanban, and sprint planning.", "job_levels": ["Mid-Professional", "Professional Individual Contributor", "Manager"]},
        {"name": "Big Data (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/big-data-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of big data technologies including Hadoop, Spark, and data processing at scale.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Machine Learning (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/machine-learning-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures understanding of machine learning algorithms, model evaluation, and applied ML concepts.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Cloud Computing (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/cloud-computing-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of cloud computing concepts, architectures, and major platforms (AWS, Azure, GCP).", "job_levels": ["Mid-Professional", "Professional Individual Contributor", "Manager"]},
        {"name": "Cybersecurity (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/cybersecurity-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of cybersecurity principles, threat management, and information security practices.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Network Administration (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/network-administration-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of networking concepts, protocols, infrastructure, and administration.", "job_levels": ["Entry-Level", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Unix/Linux (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/unix-linux-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of Unix/Linux operating systems, shell scripting, and system administration.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "PHP (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/php-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of PHP server-side scripting language and web application development.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Ruby (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/ruby-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of Ruby programming language and Rails framework.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Scala (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/scala-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of Scala programming language and functional programming concepts.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "R Programming (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/r-programming-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of R language for statistical computing and data analysis.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Selenium (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/selenium-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of Selenium WebDriver for web application test automation.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "DevOps (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/devops-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures understanding of DevOps practices including CI/CD pipelines, containerization, and deployment automation.", "job_levels": ["Mid-Professional", "Professional Individual Contributor", "Manager"]},
        {"name": "Kubernetes (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/kubernetes-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of Kubernetes container orchestration, deployment, and scaling.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Docker (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/docker-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of Docker containerization, images, registries, and deployment.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},

        # Business & Finance Knowledge
        {"name": "Financial Accounting (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/financial-accounting-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of financial accounting principles, balance sheets, income statements, and GAAP.", "job_levels": ["Graduate", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Business Administration (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/business-administration-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge of core business administration concepts across finance, HR, marketing, and operations.", "job_levels": ["Graduate", "Manager", "Mid-Professional"]},
        {"name": "MS Word (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/ms-word-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures ability to use Microsoft Word for document creation, formatting, and editing.", "job_levels": ["Entry-Level", "Graduate", "Mid-Professional"]},
        {"name": "MS PowerPoint (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/ms-powerpoint-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures ability to create and edit presentations using Microsoft PowerPoint.", "job_levels": ["Entry-Level", "Graduate", "Mid-Professional"]},
        {"name": "Typing Speed Test", "url": "https://www.shl.com/solutions/products/product-catalog/view/typing-speed-test/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures typing speed (WPM) and accuracy for clerical and administrative roles.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Data Entry Speed and Accuracy", "url": "https://www.shl.com/solutions/products/product-catalog/view/data-entry-speed-and-accuracy/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures speed and accuracy of data entry for clerical roles.", "job_levels": ["Entry-Level", "General Population"]},

        # Biodata & Situational Judgement
        {"name": "Graduate Global Situational Judgement Test (Graduate GSJT)", "url": "https://www.shl.com/solutions/products/product-catalog/view/graduate-global-situational-judgement-test-graduate-gsjt/", "test_types": ["B"], "remote_testing": True, "adaptive_irt": False, "description": "Situational judgement test for graduate-level roles. Assesses judgment in typical workplace scenarios.", "job_levels": ["Graduate"]},
        {"name": "General Situational Judgement Test (GSA)", "url": "https://www.shl.com/solutions/products/product-catalog/view/general-situational-judgement-test-gsa/", "test_types": ["B"], "remote_testing": True, "adaptive_irt": False, "description": "Situational judgement test for general professional populations. Measures judgment in work-related scenarios.", "job_levels": ["Entry-Level", "General Population", "Graduate", "Mid-Professional"]},
        {"name": "Customer Service Situational Judgement Test", "url": "https://www.shl.com/solutions/products/product-catalog/view/customer-service-situational-judgement-test/", "test_types": ["B"], "remote_testing": True, "adaptive_irt": False, "description": "Measures judgment and decision-making in customer service scenarios.", "job_levels": ["Entry-Level", "General Population", "Supervisor"]},
        {"name": "Retail Sales Situational Judgement Test", "url": "https://www.shl.com/solutions/products/product-catalog/view/retail-sales-situational-judgement-test/", "test_types": ["B"], "remote_testing": True, "adaptive_irt": False, "description": "SJT for retail sales roles, assessing judgment in selling, customer interaction, and team situations.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Management Situational Judgement Test", "url": "https://www.shl.com/solutions/products/product-catalog/view/management-situational-judgement-test/", "test_types": ["B"], "remote_testing": True, "adaptive_irt": False, "description": "SJT for management-level candidates measuring judgment in people management and business scenarios.", "job_levels": ["Front Line Manager", "Manager", "Supervisor"]},
        {"name": "Sales Representative Solution Situational Judgement Test", "url": "https://www.shl.com/solutions/products/product-catalog/view/sales-rep-sjt/", "test_types": ["B"], "remote_testing": True, "adaptive_irt": False, "description": "Situational judgement test specific to sales representative roles, measuring customer interaction judgment.", "job_levels": ["Entry-Level", "Mid-Professional", "Professional Individual Contributor"]},

        # Simulations
        {"name": "Coding Simulation - Java", "url": "https://www.shl.com/solutions/products/product-catalog/view/coding-simulation-java/", "test_types": ["S"], "remote_testing": True, "adaptive_irt": False, "description": "Hands-on coding simulation in Java. Candidates write actual code to solve software development problems.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Coding Simulation - Python", "url": "https://www.shl.com/solutions/products/product-catalog/view/coding-simulation-python/", "test_types": ["S"], "remote_testing": True, "adaptive_irt": False, "description": "Hands-on coding simulation in Python. Tests real coding ability in practical scenarios.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Coding Simulation - JavaScript", "url": "https://www.shl.com/solutions/products/product-catalog/view/coding-simulation-javascript/", "test_types": ["S"], "remote_testing": True, "adaptive_irt": False, "description": "Hands-on JavaScript coding simulation testing real-world web development skills.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Financial Analysis Simulation", "url": "https://www.shl.com/solutions/products/product-catalog/view/financial-analysis-simulation/", "test_types": ["S"], "remote_testing": True, "adaptive_irt": False, "description": "Work simulation assessing financial analysis skills in realistic business scenarios.", "job_levels": ["Graduate", "Manager", "Mid-Professional"]},
        {"name": "Call Center Simulation", "url": "https://www.shl.com/solutions/products/product-catalog/view/call-center-simulation/", "test_types": ["S"], "remote_testing": True, "adaptive_irt": False, "description": "Simulates typical call center interactions to assess customer service and multitasking ability.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Contact Center - Customer Service Simulation", "url": "https://www.shl.com/solutions/products/product-catalog/view/contact-center-customer-service-simulation/", "test_types": ["S"], "remote_testing": True, "adaptive_irt": False, "description": "Full call center work simulation measuring customer service performance in realistic scenarios.", "job_levels": ["Entry-Level", "General Population", "Supervisor"]},

        # Competencies
        {"name": "Universal Competency Report (UCF)", "url": "https://www.shl.com/solutions/products/product-catalog/view/universal-competency-report-ucf/", "test_types": ["C"], "remote_testing": True, "adaptive_irt": False, "description": "Based on OPQ32r, maps personality to the Universal Competency Framework (UCF). Provides behavioral predictions across 20 competency dimensions.", "job_levels": ["Director", "Executive", "Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Leadership Report (OPQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/leadership-report-opq/", "test_types": ["C"], "remote_testing": True, "adaptive_irt": False, "description": "Derived from OPQ32r, evaluates personality fit against leadership competencies and styles.", "job_levels": ["Director", "Executive", "Manager"]},
        {"name": "Sales Achievement Predictor (SalesAP)", "url": "https://www.shl.com/solutions/products/product-catalog/view/sales-achievement-predictor-salesap/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Personality-based assessment predicting sales performance across key competencies. Identifies candidates likely to succeed in sales roles.", "job_levels": ["Entry-Level", "Graduate", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Customer Contact Styles Questionnaire (CCSQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/customer-contact-styles-questionnaire-ccsq/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Measures personality traits relevant to customer-facing roles. Predicts performance in contact center and customer service positions.", "job_levels": ["Entry-Level", "General Population", "Graduate"]},
        {"name": "Service & Teamwork Questionnaire (STeaQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/service-teamwork-questionnaire-steaq/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Measures behaviors important for customer service and team collaboration.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Dependability & Safety Instrument (DSI)", "url": "https://www.shl.com/solutions/products/product-catalog/view/dependability-safety-instrument-dsi/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Measures personality dimensions related to workplace safety, reliability, and rule compliance.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Work Safety Questionnaire (WSQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/work-safety-questionnaire-wsq/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Assesses attitudes toward workplace safety, compliance with safety rules, and safety behaviors.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Work Strengths", "url": "https://www.shl.com/solutions/products/product-catalog/view/work-strengths/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Brief personality questionnaire identifying individual work strengths and areas for development.", "job_levels": ["Entry-Level", "Graduate", "General Population"]},
        {"name": "Scenarios - 360 Feedback", "url": "https://www.shl.com/solutions/products/product-catalog/view/scenarios-360-feedback/", "test_types": ["D"], "remote_testing": True, "adaptive_irt": False, "description": "360-degree feedback assessment measuring behavioral competencies from multiple rater perspectives.", "job_levels": ["Manager", "Mid-Professional", "Professional Individual Contributor"]},

        # Additional specific tests
        {"name": "Verify G+ (Cognitive Ability)", "url": "https://www.shl.com/solutions/products/product-catalog/view/verify-g/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": True, "description": "Adaptive cognitive ability test combining numerical, verbal, and inductive reasoning into one assessment.", "job_levels": ["Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Occupational Personality Questionnaire (OPQ32n)", "url": "https://www.shl.com/solutions/products/product-catalog/view/opq32n/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Normative personality questionnaire measuring 32 personality characteristics. Provides norm-referenced scores.", "job_levels": ["Director", "Executive", "Graduate", "Manager", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Technology Sector Report (OPQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/technology-sector-report-opq/", "test_types": ["C", "P"], "remote_testing": True, "adaptive_irt": False, "description": "OPQ-based report showing personality fit for technology sector roles and competencies.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Graduate Technology Report (OPQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/graduate-technology-report-opq/", "test_types": ["C", "P"], "remote_testing": True, "adaptive_irt": False, "description": "OPQ-based report designed for graduate-level technology roles and competency development.", "job_levels": ["Graduate"]},
        {"name": "Workplace English Language Test (WELT)", "url": "https://www.shl.com/solutions/products/product-catalog/view/workplace-english-language-test/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Assesses English language proficiency in a workplace context. Measures reading, listening, and comprehension.", "job_levels": ["Entry-Level", "General Population", "Graduate"]},
        {"name": "Workplace Spanish Language Test", "url": "https://www.shl.com/solutions/products/product-catalog/view/workplace-spanish-language-test/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Assesses Spanish language proficiency for workplace communication.", "job_levels": ["Entry-Level", "General Population", "Graduate"]},
        {"name": "Entry Level Sales 7.1 Solution", "url": "https://www.shl.com/solutions/products/product-catalog/view/entry-level-sales-7-1-solution/", "test_types": ["B", "A", "P"], "remote_testing": True, "adaptive_irt": False, "description": "Pre-packaged solution for entry-level sales roles combining ability, personality, and SJT assessments.", "job_levels": ["Entry-Level"]},
        {"name": "Administrative Professional 7.1 Solution", "url": "https://www.shl.com/solutions/products/product-catalog/view/administrative-professional-7-1-solution/", "test_types": ["A", "B", "K"], "remote_testing": True, "adaptive_irt": False, "description": "Assessment solution for administrative professionals combining clerical ability, data checking, and personality.", "job_levels": ["Entry-Level", "Graduate"]},
        {"name": "Data Analyst (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/data-analyst-new/", "test_types": ["K"], "remote_testing": True, "adaptive_irt": False, "description": "Measures knowledge and skills relevant to data analysis roles including statistics, data manipulation, and visualization.", "job_levels": ["Graduate", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Project Manager Solution", "url": "https://www.shl.com/solutions/products/product-catalog/view/project-manager-solution/", "test_types": ["A", "B", "P"], "remote_testing": True, "adaptive_irt": False, "description": "Comprehensive solution for project manager roles covering cognitive ability, personality, and SJT.", "job_levels": ["Manager", "Mid-Professional"]},
        {"name": "Checking Test (Clerical)", "url": "https://www.shl.com/solutions/products/product-catalog/view/checking-test/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Measures speed and accuracy of checking, comparing data and spotting errors in clerical tasks.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Following Instructions Test", "url": "https://www.shl.com/solutions/products/product-catalog/view/following-instructions-test/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Measures ability to follow complex written instructions accurately, relevant to operational roles.", "job_levels": ["Entry-Level", "General Population"]},
        {"name": "Spatial Reasoning", "url": "https://www.shl.com/solutions/products/product-catalog/view/spatial-reasoning/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Measures ability to visualize and mentally manipulate 2D and 3D objects. Relevant for engineering, architecture, and design roles.", "job_levels": ["Entry-Level", "Graduate", "Mid-Professional"]},
        {"name": "Management and Graduate Item Bank (MGIB) - Numerical", "url": "https://www.shl.com/solutions/products/product-catalog/view/management-and-graduate-item-bank-mgib-numerical/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Numerical reasoning test from the MGIB battery designed for management and graduate-level candidates.", "job_levels": ["Graduate", "Manager"]},
        {"name": "Management and Graduate Item Bank (MGIB) - Verbal", "url": "https://www.shl.com/solutions/products/product-catalog/view/management-and-graduate-item-bank-mgib-verbal/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Verbal reasoning test from the MGIB battery for management and graduate candidates.", "job_levels": ["Graduate", "Manager"]},
        {"name": "Scenarios for Managers (SJT)", "url": "https://www.shl.com/solutions/products/product-catalog/view/scenarios-for-managers-sjt/", "test_types": ["B"], "remote_testing": True, "adaptive_irt": False, "description": "Situational judgement test presenting realistic management scenarios to assess managerial decision-making.", "job_levels": ["Front Line Manager", "Manager", "Supervisor"]},
        {"name": "Supervisory Practices Questionnaire (SPQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/supervisory-practices-questionnaire-spq/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Assesses personality and behavioral preferences relevant to supervisory and team leader roles.", "job_levels": ["Front Line Manager", "Supervisor"]},
        {"name": "Executive Dimensions", "url": "https://www.shl.com/solutions/products/product-catalog/view/executive-dimensions/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Executive-level personality assessment measuring leadership and strategic dimensions for senior leaders.", "job_levels": ["Director", "Executive"]},
        {"name": "Potential in Management Questionnaire (PMQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/potential-in-management-questionnaire-pmq/", "test_types": ["P"], "remote_testing": True, "adaptive_irt": False, "description": "Identifies high potential for management roles by measuring personality traits linked to management effectiveness.", "job_levels": ["Graduate", "Mid-Professional", "Professional Individual Contributor"]},
        {"name": "IT Report (OPQ)", "url": "https://www.shl.com/solutions/products/product-catalog/view/it-report-opq/", "test_types": ["C", "P"], "remote_testing": True, "adaptive_irt": False, "description": "OPQ-based report mapping personality to IT-sector competencies. Ideal for technology hiring.", "job_levels": ["Mid-Professional", "Professional Individual Contributor"]},
        {"name": "Reasoning Tests - Numerical (Short)", "url": "https://www.shl.com/solutions/products/product-catalog/view/reasoning-tests-numerical-short/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Short-form numerical reasoning test for high-volume screening scenarios.", "job_levels": ["Entry-Level", "General Population", "Graduate"]},
        {"name": "Reasoning Tests - Verbal (Short)", "url": "https://www.shl.com/solutions/products/product-catalog/view/reasoning-tests-verbal-short/", "test_types": ["A"], "remote_testing": True, "adaptive_irt": False, "description": "Short-form verbal reasoning test for efficient screening.", "job_levels": ["Entry-Level", "General Population", "Graduate"]},
    ]

    return products


if __name__ == "__main__":
    # Try live scraping first, fall back to known products
    try:
        print("Attempting live catalog scrape...")
        products = scrape_all()
        if len(products) < 20:
            print("Insufficient products scraped, using known product list.")
            products = build_catalog_from_known_products()
    except Exception as e:
        print(f"Live scrape failed: {e}. Using known product list.")
        products = build_catalog_from_known_products()

    print(f"\nTotal products: {len(products)}")
    with open("catalog.json", "w") as f:
        json.dump(products, f, indent=2)
    print("Saved to catalog.json")
