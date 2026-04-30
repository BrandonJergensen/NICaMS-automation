import re
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# =========================================================
# CONFIG
# =========================================================
LOGIN_URL = "https://dcs-nicams.ne.gov/inmates/websuite/inmateSearchResults.xhtml"
USERNAME = "bjergen-001"

# Trial input from CSV
CSV_RECORD = {
    "fname": "ALLEN",
    "lname": "ZOLLICOFFER",
    "dob": "06/02/1967",   # MM/DD/YYYY
    "id": None,            # or "214359"
}

# If True, first pass searches with Active checked.
# If nothing usable is found, the script retries with Active unchecked.
TRY_ACTIVE_FIRST = True

# Browser options
options = Options()
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 20)

PROGRAM_NAME_VALUES = {
    "3 MCC Core Courses": "233",
    "Associate Degree": "168",
    "Career Certification": "123",
    "CDL Preparation": "169",
    "Employment Readiness": "237",
    "Forklift Certification": "171",
    "Four-Week Workshop": "172",
    "Initial Communication": "239",
    "Job Readiness": "174",
    "Long-Term Relief Group": "175",
    "MCC Certificate of Completion-Credit": "314",
    "MCC Certificate of Completion-Noncredit": "315",
    "MCC Credit Course": "177",
    "National Career Readiness Certificate": "178",
    "Non-Credit Workshop": "180",
    "Orientation": "181",
    "OSHA": "182",
    "Other Services": "183",
    "Trauma Informed Peer Support": "240",
}

VLS_GRANT_VALUES = {
    "Yes": "9269200",
    "No": "9269201",
}

ACCEPTED_REFUSED_VALUES = {
    "Accepted": "827000",
    "Refused": "827001",
    "No Response": "827002",
}

LOCATION_VALUES = {
    "CCL": "826000",
    "CCO": "826001",
    "CSI": "826014",
    "Community": "826013",
    "NCW": "826004",
    "NCY": "826005",
    "NSP": "826006",
    "OCC": "826007",
    "RTC": "826011",
    "TSC": "826008",
    "VLS": "826012",
    "WEC": "826009",
}

PROGRAM_OUTCOME_VALUES = {
    "Satisfactory Completion": "829000",
    "Terminated from Program": "829001",
    "Withdrawn from Program": "829002",
}
# =========================================================
# HELPERS: GENERAL
# =========================================================
def debug(msg: str) -> None:
    print(f"[DEBUG] {msg}")


def safe_click(element) -> None:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.2)
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def clear_and_type(element, value: Optional[str]) -> None:
    safe_click(element)
    try:
        element.clear()
    except Exception:
        pass
    element.send_keys(Keys.CONTROL + "a")
    element.send_keys(Keys.BACKSPACE)
    if value:
        element.send_keys(str(value))


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    s = date_str.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%m/%d/%Y")
    except ValueError:
        return None


def normalize_name(name: Optional[str]) -> str:
    if not name:
        return ""
    name = name.strip().upper()
    name = re.sub(r"\s+", " ", name)
    return name


def meaningful_segments(name: Optional[str]) -> List[str]:
    n = normalize_name(name)
    parts = re.split(r"[^A-Z0-9]+", n)
    return [p for p in parts if len(p) >= 3]


def best_search_token(name: Optional[str]) -> str:
    parts = meaningful_segments(name)
    if not parts:
        return normalize_name(name)
    return max(parts, key=len)


# =========================================================
# HELPERS: LOGIN / NAVIGATION
# =========================================================
def login_and_open_nicams():
    debug("Opening login page...")
    driver.get(LOGIN_URL)
    driver.maximize_window()

    debug("Waiting for username field...")
    username_box = wait.until(
        EC.presence_of_element_located((By.ID, "loginForm:userName"))
    )
    clear_and_type(username_box, USERNAME)

    debug("Waiting for password field...")
    wait.until(
        EC.presence_of_element_located((By.ID, "loginForm:password"))
    )

    print("\nEnter your password in the browser.")
    input("Press Enter AFTER you have typed your password...")

    debug("Clicking login...")
    login_button = wait.until(
        EC.element_to_be_clickable((By.ID, "loginForm:btnLogin"))
    )
    safe_click(login_button)

    debug("Login submitted. Waiting briefly for redirect...")
    time.sleep(3)

    current_url = driver.current_url
    debug(f"Current URL after login: {current_url}")
    debug(f"Page title after login: {driver.title}")

    # Case 1: already inside NICaMS search page
    if "inmateSearchResults" in current_url:
        debug("Already inside NICaMS system. No need to click link.")
        return

    # Case 2: still on landing page, need to click the link
    try:
        debug("Looking for NICaMS link...")
        nicams_link = wait.until(
            EC.element_to_be_clickable((By.LINK_TEXT, "NICaMS Data Entry and Inquiry"))
        )

        debug("Clicking NICaMS link...")
        driver.execute_script("arguments[0].click();", nicams_link)

        debug("Waiting for new tab...")
        wait.until(lambda d: len(d.window_handles) > 1)
        driver.switch_to.window(driver.window_handles[-1])

        debug("Switched to NICaMS tab.")
        debug(f"Final URL: {driver.current_url}")
        debug(f"Final title: {driver.title}")

    except Exception as e:
        debug(f"NICaMS link path failed: {type(e).__name__}: {e}")
        debug("Continuing without link click.")


# =========================================================
# HELPERS: SEARCH PAGE
# Based on the structure you shared for:
# - ID quick lookup
# - Last Name / First Name / DOB
# - Active checkbox
# - Exact DOB checkbox
# - Search button
# :contentReference[oaicite:1]{index=1}
# =========================================================
def set_checkbox_state(checkbox_input_id: str, should_be_checked: bool) -> None:
    cb = wait.until(EC.presence_of_element_located((By.ID, checkbox_input_id)))
    current = cb.is_selected()
    if current != should_be_checked:
        safe_click(cb)
        time.sleep(0.3)


def wait_for_ajax_refresh() -> None:
    # PrimeFaces wait dialog exists on this page
    # Give it a moment to appear/disappear if the request is quick
    time.sleep(0.75)
    try:
        wait.until(
            EC.invisibility_of_element_located((By.ID, "inmateSearchId:pdial1"))
        )
    except Exception:
        pass
    time.sleep(0.75)


def clear_basic_search() -> None:
    clear_btn = wait.until(
        EC.element_to_be_clickable((By.ID, "inmateSearchId:inmateSearchForm:cancelSearch"))
    )
    safe_click(clear_btn)
    wait_for_ajax_refresh()


def search_by_id(id_value: str) -> None:
    debug(f"Searching by ID: {id_value}")

    id_box = wait.until(
        EC.presence_of_element_located((By.ID, "inmateSearchId:inmateLookupForm:idSearchParam1"))
    )
    clear_and_type(id_box, id_value)

    go_btn = wait.until(
        EC.element_to_be_clickable((By.ID, "inmateSearchId:inmateLookupForm:inmateLookupById1"))
    )
    safe_click(go_btn)
    wait_for_ajax_refresh()


def search_by_name_dob(last_name: str, first_name: str, dob_mmddyyyy: str,
                       active_checked: bool = True, exact_dob: bool = True) -> None:
    debug(f"Searching by name/DOB | lname={last_name}, fname={first_name}, dob={dob_mmddyyyy}, active={active_checked}, exact_dob={exact_dob}")

    clear_basic_search()

    last_box = wait.until(
        EC.presence_of_element_located((By.ID, "inmateSearchId:inmateSearchForm:inmateSearchlastName"))
    )
    first_box = wait.until(
        EC.presence_of_element_located((By.ID, "inmateSearchId:inmateSearchForm:inmateSearchFirstName"))
    )
    dob_box = wait.until(
        EC.presence_of_element_located((By.ID, "inmateSearchId:inmateSearchForm:inmateSearchDob_input"))
    )

    clear_and_type(last_box, last_name)
    clear_and_type(first_box, first_name)
    clear_and_type(dob_box, dob_mmddyyyy)
    dob_box.send_keys(Keys.TAB)

    set_checkbox_state("inmateSearchId:inmateSearchForm:inmateSearchActive_input", active_checked)
    set_checkbox_state("inmateSearchId:inmateSearchForm:inmateSearchExactDob_input", exact_dob)

    search_btn = wait.until(
        EC.element_to_be_clickable((By.ID, "inmateSearchId:inmateSearchForm:inmateSearch"))
    )
    safe_click(search_btn)
    wait_for_ajax_refresh()


# =========================================================
# HELPERS: RESULTS EXTRACTION
# Trial version:
# We assume the visible results grid has rows where:
# col 0 = checkbox
# col 1 = ID
# col 2 = Last
# col 3 = First
# col 4 = MI
# col 5 = DOB
# col 6 = Race
# col 7 = Prev ID
# col 8 = WEC A-Nbr
# col 9 = SID
# col10 = FBI
# col11 = Date Rcv'd
# col12 = Date Rlsd
# col13 = FAC
# col14 = LOC
#
# This matches the screenshot you shared visually.
# =========================================================
def get_result_rows():
    """
    Find likely inmate result rows by looking for rows that:
    - have at least 15 cells
    - have a clickable link in column 1 (ID column)
    - look like actual data rows rather than headers/menu blocks
    """
    rows = driver.find_elements(By.TAG_NAME, "tr")
    good_rows = []

    for row in rows:
        try:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) < 15:
                continue

            # Column 1 should usually contain the inmate ID link
            id_links = cols[1].find_elements(By.TAG_NAME, "a")
            if not id_links:
                continue

            id_text = cols[1].text.strip()
            lname = cols[2].text.strip()
            fname = cols[3].text.strip()
            dob = cols[5].text.strip()
            date_rcvd = cols[11].text.strip()
            date_rlsd = cols[12].text.strip()
            fac = cols[13].text.strip()
            loc = cols[14].text.strip()

            # Filter out obvious junk/header/menu rows
            junk_tokens = {
                "CASE PLAN", "SEARCH", "ADDL SEARCH", "GO TO",
                "INMATE LOOKUP", "INMATE SEARCH RESULTS"
            }

            combined = " ".join([
                id_text.upper(), lname.upper(), fname.upper(),
                dob.upper(), date_rcvd.upper(), date_rlsd.upper(),
                fac.upper(), loc.upper()
            ])

            if any(token in combined for token in junk_tokens):
                continue

            # keep only rows that look like inmate result rows
            good_rows.append(row)

        except Exception:
            continue

    return good_rows


def extract_candidates():
    rows = get_result_rows()
    debug(f"Found {len(rows)} likely result row(s)")

    candidates = []

    for idx, row in enumerate(rows):
        try:
            cols = row.find_elements(By.TAG_NAME, "td")
            id_link = cols[1].find_element(By.TAG_NAME, "a")

            candidate = {
                "row_index": idx,
                "row_element": row,
                "id": cols[1].text.strip(),
                "id_link": id_link,
                "lname": cols[2].text.strip(),
                "fname": cols[3].text.strip(),
                "mi": cols[4].text.strip(),
                "dob": cols[5].text.strip(),
                "race": cols[6].text.strip(),
                "prev_id": cols[7].text.strip(),
                "wec_a_nbr": cols[8].text.strip(),
                "sid": cols[9].text.strip(),
                "fbi": cols[10].text.strip(),
                "date_rcvd": cols[11].text.strip(),
                "date_rlsd": cols[12].text.strip(),
                "fac": cols[13].text.strip(),
                "loc": cols[14].text.strip(),
            }

            candidates.append(candidate)

        except Exception as e:
            debug(f"Skipping row {idx} due to extraction error: {e}")

    return candidates

def print_candidates(candidates: List[Dict[str, Any]]) -> None:
    print("\n========== EXTRACTED CANDIDATES ==========")
    for i, c in enumerate(candidates, start=1):
        print(
            f"{i}. ID={c['id']} | LNAME={c['lname']} | FNAME={c['fname']} | "
            f"DOB={c['dob']} | PREV_ID={c['prev_id']} | "
            f"DATE_RCVD={c['date_rcvd']} | DATE_RLSD={c['date_rlsd']} | "
            f"FAC={c['fac']} | LOC={c['loc']}"
        )
    print("==========================================\n")

def open_selected_candidate(details):
    candidate = details.get("candidate")

    if not candidate:
        print("No candidate to open.")
        return

    id_link = candidate.get("id_link")

    if not id_link:
        print(f"No clickable ID link found for ID={candidate.get('id')}")
        return

    print(f"Opening selected ID: {candidate.get('id')}")
    safe_click(id_link)
    wait_for_ajax_refresh()

    print("Opened selected candidate.")
    print("Current URL:", driver.current_url)
    print("Page title:", driver.title)

# Your hard rule:
# release older than 18 months and not active = hard no
# =========================================================
def is_active_loc(loc: Optional[str]) -> bool:
    if not loc:
        return False
    loc_u = loc.strip().upper()

    # Explicit active statuses
    if loc_u in {"PROL", "PRS"}:
        return True

    # Heuristic for housing-like codes:
    # If it contains digits and letters/spaces, treat as active housing/unit.
    # You can tighten this later.
    if any(ch.isdigit() for ch in loc_u):
        return True

    return False


def candidate_is_eligible(candidate: Dict[str, Any]) -> Tuple[bool, str]:
    loc = candidate.get("loc", "")
    if is_active_loc(loc):
        return True, "active_location"

    rlsd = parse_date(candidate.get("date_rlsd"))
    if rlsd is None:
        return False, "inactive_and_no_release_date"

    cutoff = datetime.now() - timedelta(days=548)  # ~18 months
    if rlsd < cutoff:
        return False, "released_over_18_months_ago_and_not_active"

    return True, "released_within_18_months"


def name_match_score(csv_value: str, cand_value: str) -> int:
    csv_norm = normalize_name(csv_value)
    cand_norm = normalize_name(cand_value)

    if not csv_norm or not cand_norm:
        return 0

    if csv_norm == cand_norm:
        return 25

    # Segment-based partial logic
    csv_segments = meaningful_segments(csv_norm)
    cand_segments = meaningful_segments(cand_norm)

    if set(csv_segments) & set(cand_segments):
        return 12

    # simple containment fallback
    if csv_norm in cand_norm or cand_norm in csv_norm:
        return 8

    return 0


def score_candidate(csv_record: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[int, List[str]]:
    reasons = []
    score = 0

    # DOB exact required for v1
    if normalize_name(csv_record["dob"]) != normalize_name(candidate["dob"]):
        return -999, ["dob_mismatch_hard_fail"]

    score += 40
    reasons.append("dob_exact(+40)")

    # ID exact
    csv_id = csv_record.get("id")
    if csv_id:
        if str(csv_id).strip() == str(candidate.get("id", "")).strip():
            score += 45
            reasons.append("id_exact(+45)")
        elif str(csv_id).strip() == str(candidate.get("prev_id", "")).strip():
            score += 20
            reasons.append("prev_id_match(+20)")

    # Last / first name
    lname_pts = name_match_score(csv_record["lname"], candidate["lname"])
    if lname_pts:
        score += lname_pts
        reasons.append(f"lname_match(+{lname_pts})")

    fname_pts = name_match_score(csv_record["fname"], candidate["fname"])
    if fname_pts:
        # first name should count a bit less than last name in your use case
        fname_adjusted = 18 if fname_pts == 25 else 8
        score += fname_adjusted
        reasons.append(f"fname_match(+{fname_adjusted})")

    # active boost
    if is_active_loc(candidate.get("loc", "")):
        score += 20
        reasons.append("active_loc(+20)")
    else:
        score += 8
        reasons.append("recent_release_nonactive(+8)")

    return score, reasons


def apply_relationship_adjustments(candidates: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    id_map = {}
    for c in candidates:
        cid = str(c.get("id", "")).strip()
        if cid:
            id_map[cid] = c

    adjustments = {id(c): {"score_delta": 0, "reasons": []} for c in candidates}

    for c in candidates:
        prev_id = str(c.get("prev_id", "")).strip()
        if prev_id and prev_id in id_map:
            adjustments[id(c)]["score_delta"] += 30
            adjustments[id(c)]["reasons"].append("prev_id_points_to_another_candidate(+30)")

            older = id_map[prev_id]
            adjustments[id(older)]["score_delta"] -= 10
            adjustments[id(older)]["reasons"].append("is_previous_record_of_other_candidate(-10)")

    return adjustments


def decide_match(csv_record: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Tuple[str, Any]:
    eligible = []
    rejected = []

    for c in candidates:
        ok, why = candidate_is_eligible(c)
        if ok:
            eligible.append(c)
        else:
            rejected.append((c, why))

    print("\n========== ELIGIBILITY FILTER ==========")
    for c, why in rejected:
        print(f"REJECTED ID={c['id']} | reason={why}")
    print("========================================\n")

    if not eligible:
        return "NO_MATCH", {"reason": "no_eligible_candidates"}

    scored = []
    for c in eligible:
        s, reasons = score_candidate(csv_record, c)
        if s > -999:
            scored.append((c, s, reasons))
        else:
            print(f"HARD FAIL SCORE ID={c['id']} | reasons={reasons}")

    if not scored:
        return "NO_MATCH", {"reason": "no_candidates_after_scoring"}

    scored.sort(key=lambda x: x[1], reverse=True)

    print("========== SCORED CANDIDATES ==========")
    for c, s, reasons in scored:
        print(f"ID={c['id']} | score={s} | reasons={', '.join(reasons)}")
    print("=======================================\n")

    best_c, best_score, best_reasons = scored[0]

    if best_score < 60:
        return "NO_MATCH", {
            "reason": "best_score_below_threshold",
            "best_id": best_c["id"],
            "best_score": best_score,
        }

    if len(scored) > 1:
        second_c, second_score, _ = scored[1]
        if best_score - second_score < 15:
            return "REVIEW", {
                "reason": "top_two_too_close",
                "best_id": best_c["id"],
                "best_score": best_score,
                "second_id": second_c["id"],
                "second_score": second_score,
                "scored": scored,
            }

    if best_score >= 85:
        return "AUTO", {
            "candidate": best_c,
            "score": best_score,
            "reasons": best_reasons,
        }

    return "REVIEW", {
        "reason": "best_score_not_high_enough_for_auto",
        "best_id": best_c["id"],
        "best_score": best_score,
        "reasons": best_reasons,
        "scored": scored,
    }

# =========================================================
# SEARCH STRATEGY
# =========================================================
def run_trial_search(csv_record: Dict[str, Any]) -> Tuple[str, Any, List[Dict[str, Any]]]:
    # 1. If ID exists, try ID lookup first
    if csv_record.get("id"):
        search_by_id(csv_record["id"])
        candidates = extract_candidates()
        print_candidates(candidates)
        decision, details = decide_match(csv_record, candidates)
        return decision, details, candidates

    # 2. Exact name + DOB with Active checked
    search_by_name_dob(
        last_name=csv_record["lname"],
        first_name=csv_record["fname"],
        dob_mmddyyyy=csv_record["dob"],
        active_checked=TRY_ACTIVE_FIRST,
        exact_dob=True,
    )
    candidates = extract_candidates()
    print_candidates(candidates)

    decision, details = decide_match(csv_record, candidates)

    # 3. If nothing usable, retry with Active unchecked
    if decision == "NO_MATCH":
        print("\nRetrying with Active unchecked...\n")
        search_by_name_dob(
            last_name=csv_record["lname"],
            first_name=csv_record["fname"],
            dob_mmddyyyy=csv_record["dob"],
            active_checked=False,
            exact_dob=True,
        )
        candidates = extract_candidates()
        print_candidates(candidates)
        decision, details = decide_match(csv_record, candidates)

    # 4. If still no match, try best-segment fallback
    if decision == "NO_MATCH":
        print("\nRetrying with segment-based name tokens...\n")
        lname_token = best_search_token(csv_record["lname"])
        fname_token = best_search_token(csv_record["fname"])
        search_by_name_dob(
            last_name=lname_token,
            first_name=fname_token,
            dob_mmddyyyy=csv_record["dob"],
            active_checked=False,
            exact_dob=True,
        )
        candidates = extract_candidates()
        print_candidates(candidates)
        decision, details = decide_match(csv_record, candidates)

    return decision, details, candidates

# =========================================================
# HELPERS: non-clinical program tracking
# Based on the structure you shared for:
# - for filling out (and navigating to) the non-clinical program tracking page
# =========================================================

def go_to_non_clinical_program_tracking():
    print("Navigating to Non-Clinical Program Tracking...")

    try:
        # Most reliable: match exact visible text
        menu_item = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//a[normalize-space()='Non-Clinical Program Tracking']"
            ))
        )

    except:
        # Fallback (in case it's not an <a> tag)
        menu_item = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[normalize-space()='Non-Clinical Program Tracking']"
            ))
        )

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", menu_item)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", menu_item)

    wait_for_ajax_refresh()

    print("Navigated to Non-Clinical Program Tracking.")
    print("Current URL:", driver.current_url)
    print("Page title:", driver.title)

from selenium.webdriver.support.ui import Select

AUTO_SUBMIT_NONCLINICAL = False

CSV_ROW = {
    "section_title": "RENT Forklift Certification",
    "section_start_date": "4/10/2026",
    "section_end_date": "4/10/2026",
}

def set_date_input(input_id, value, required=True):
    elem = wait.until(EC.presence_of_element_located((By.ID, input_id)))

    # If disabled, wait a little for AJAX to unlock it
    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.find_element(By.ID, input_id).get_attribute("disabled") is None
        )
        elem = driver.find_element(By.ID, input_id)
    except Exception:
        if required:
            raise Exception(f"{input_id} is still disabled, cannot enter date.")
        print(f"{input_id} is disabled, skipping.")
        return False

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
    elem.click()
    elem.send_keys(Keys.CONTROL + "a")
    elem.send_keys(Keys.BACKSPACE)
    elem.send_keys(value)
    elem.send_keys(Keys.TAB)
    wait_for_ajax_refresh()
    return True

def select_primefaces_dropdown_by_label(hidden_select_id, visible_text):
    """
    Works with PrimeFaces selectOneMenu by using the hidden real <select>,
    then firing change events.
    """
    select_elem = wait.until(EC.presence_of_element_located((By.ID, hidden_select_id)))

    driver.execute_script("""
        const select = arguments[0];
        const text = arguments[1];

        let found = false;
        for (const option of select.options) {
            if (option.text.trim() === text.trim()) {
                select.value = option.value;
                found = true;
                break;
            }
        }

        if (!found) {
            throw new Error("Option not found: " + text);
        }

        select.dispatchEvent(new Event('change', { bubbles: true }));
    """, select_elem, visible_text)

    wait_for_ajax_refresh()

def click_add_nonclinical():
    add_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[@title='Add Non-Clinical Program Tracking']"))
    )
    safe_click(add_button)
    wait_for_ajax_refresh()

def map_program_name(section_title):
    title = section_title.upper()
    if "FORKLIFT" in title:
        return "Forklift Certification"
    return None

def debug_dropdown_options(hidden_select_id):
    print(f"\n--- Debugging dropdown: {hidden_select_id} ---")

    select_elem = wait.until(
        EC.presence_of_element_located((By.ID, hidden_select_id))
    )

    options = select_elem.find_elements(By.TAG_NAME, "option")

    print(f"Found {len(options)} options:")
    for opt in options:
        print(f"value={opt.get_attribute('value')} | text={opt.text}")

    print("--- End dropdown debug ---\n")

def select_primefaces_dropdown_by_label(hidden_select_id, visible_text):
    select_elem = wait.until(
        EC.presence_of_element_located((By.ID, hidden_select_id))
    )

    driver.execute_script("""
        const select = arguments[0];
        const wanted = arguments[1].trim().toUpperCase();

        let found = false;

        for (const option of select.options) {
            const text = option.text.trim().toUpperCase();

            if (text === wanted || text.includes(wanted) || wanted.includes(text)) {
                select.value = option.value;
                found = true;
                break;
            }
        }

        if (!found) {
            const available = Array.from(select.options).map(o => o.text.trim()).join(", ");
            throw new Error("Option not found: " + arguments[1] + " | Available: " + available);
        }

        select.dispatchEvent(new Event('change', { bubbles: true }));
        select.dispatchEvent(new Event('input', { bubbles: true }));

        if (typeof PrimeFaces !== 'undefined') {
            $(select).trigger('change');
        }
    """, select_elem, visible_text)

    wait_for_ajax_refresh()

def select_primefaces_dropdown_by_value(hidden_select_id, value):
    select_elem = wait.until(
        EC.presence_of_element_located((By.ID, hidden_select_id))
    )

    # hidden_select_id example: acceptedRefusedInput_input
    widget_base_id = hidden_select_id.replace("_input", "")

    driver.execute_script("""
        const select = arguments[0];
        const widgetBaseId = arguments[1];
        const value = arguments[2];

        const widgetVar =
            "widget_" + widgetBaseId.replaceAll(":", "_");

        if (typeof PrimeFaces !== "undefined" && PrimeFaces.widgets[widgetVar]) {
            PrimeFaces.widgets[widgetVar].selectValue(value);
        } else {
            select.value = value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
            select.dispatchEvent(new Event("input", { bubbles: true }));
            if (typeof $ !== "undefined") {
                $(select).trigger("change");
            }
        }
    """, select_elem, widget_base_id, value)

    wait_for_ajax_refresh()

    # Verify
    actual = select_elem.get_attribute("value")
    print(f"{hidden_select_id} selected value now: {actual}")

def force_primefaces_change(source_id, update_targets):
    print(f"Forcing AJAX change for {source_id}...")

    driver.execute_script("""
        const sourceId = arguments[0];
        const updateTargets = arguments[1];

        const el = document.getElementById(sourceId + '_input') || document.getElementById(sourceId);

        if (el) {
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }

        if (typeof PrimeFaces !== 'undefined') {
            PrimeFaces.ab({
                s: sourceId,
                e: 'change',
                f: 'nonClinicalProgramTrackingForm',
                p: sourceId,
                u: updateTargets,
                rv: true,
                pa: [{name: 'bypassValidation', value: 'true'}]
            });
        }
    """, source_id, update_targets)

    wait_for_ajax_refresh()
    time.sleep(2)

def fill_nonclinical_form(csv_row, offered_location="Community"):
    section_start = csv_row["section_start_date"]
    section_end = csv_row["section_end_date"]

    program_name = map_program_name(csv_row["section_title"])
    if not program_name:
        raise Exception(f"No program mapping for section title: {csv_row['section_title']}")

    print("Clicking Add...")
    click_add_nonclinical()

    print("Selecting Program Classification...")
    select_primefaces_dropdown_by_label("programClassificationInput_input", "Post-Secondary")
    time.sleep(1)

    print("Selecting Program Type...")
    select_primefaces_dropdown_by_label("ProgramTypeInput_input", "Metro 180 RAP")
    time.sleep(1)

    print("Selecting Program Name...")
    select_primefaces_dropdown_by_value(
        "ProgramNameInput_input",
        PROGRAM_NAME_VALUES[program_name]
    )
    time.sleep(1)

    print("Forcing Program Name AJAX change...")
    force_primefaces_change(
        "ProgramNameInput",
        "vlsGrantInputPanel referralDateInputPanel offeredDateInputPanel acceptedRefusedInputPanel startDateInputPanel endDateInputPanel programOutcomeInputPanel"
    )

    time.sleep(2)

    print("Re-selecting Program Name after AJAX...")
    select_primefaces_dropdown_by_value(
        "ProgramNameInput_input",
        PROGRAM_NAME_VALUES[program_name]
    )
    time.sleep(1)

    print("Selecting VLS Grant...")
    select_primefaces_dropdown_by_value(
        "vlsGrantInput_input",
        VLS_GRANT_VALUES["Yes"]
    )
    time.sleep(1)

    print("Setting Referral Date...")
    set_date_input("referralDateInput_input", section_start)
    time.sleep(1)

    print("Selecting Referred By: Individual Request...")
    referred_by = wait.until(
        EC.presence_of_element_located((By.ID, "referredById:2"))
    )
    safe_click(referred_by)
    time.sleep(1)

    print("Setting Date Offered...")
    set_date_input("offeredDateInput_input", section_start)
    time.sleep(1)

    print("Resetting Accepted/Refused...")
    select_primefaces_dropdown_by_value(
        "acceptedRefusedInput_input",
        "0"
    )
    time.sleep(1)

    print("Re-setting Date Offered...")
    set_date_input("offeredDateInput_input", section_start)
    time.sleep(1)

    print("Selecting Accepted...")
    select_primefaces_dropdown_by_value(
        "acceptedRefusedInput_input",
        ACCEPTED_REFUSED_VALUES["Accepted"]
    )
    time.sleep(2)

    print("Forcing Accepted/Refused AJAX change...")
    driver.execute_script("""
    const el = document.getElementById('acceptedRefusedInput_input');
    el.dispatchEvent(new Event('change', { bubbles: true }));
    if (typeof PrimeFaces !== 'undefined') {
        PrimeFaces.ab({
            s: 'acceptedRefusedInput',
            e: 'change',
            f: 'nonClinicalProgramTrackingForm',
            p: 'acceptedRefusedInput',
            u: 'addAcceptanceRefusalTrackingId acceptanceOrRefusalDateInputPanel offeredLocationCodeInputPanel startDateInputPanel endDateInputPanel programOutcomeInputPanel',
            rv: true,
            pa: [{name: 'bypassValidation', value: 'true'}]
        });
    }
    """)
    wait_for_ajax_refresh()
    time.sleep(2)

    print("Setting Acceptance/Refusal Date...")
    set_date_input("acceptanceOrRefusalDateInputId_input", section_start, required=False)
    time.sleep(1)

    print("Selecting Offered at Location...")
    select_primefaces_dropdown_by_value(
        "offeredAtLocationInput_input",
        LOCATION_VALUES[offered_location]
    )
    time.sleep(1)

    force_primefaces_change(
        "offeredAtLocationInput",
        "startDateInputPanel startLocationInputPanel endDateInputPanel completionLocationInputPanel programOutcomeInputPanel"
    )

    print("Debug Start Location options...")
    debug_dropdown_options("startLocationInput_input")

    print("Selecting Start Location...")
    select_primefaces_dropdown_by_value(
        "startLocationInput_input",
        LOCATION_VALUES[offered_location]
    )
    time.sleep(1)

    force_primefaces_change(
        "startLocationInput",
        "startDateInputPanel endDateInputPanel completionLocationInputPanel programOutcomeInputPanel"
    )

    print("Setting Start Date...")
    set_date_input("startDateInput_input", section_start, required=False)
    time.sleep(1)

    force_primefaces_change(
        "startDateInput",
        "endDateInputPanel completionLocationInputPanel programOutcomeInputPanel"
    )

    print("Setting End Date...")
    set_date_input("endDateInput_input", section_end, required=False)
    time.sleep(1)

    print("Debug Completion Location options...")
    debug_dropdown_options("completionLocationInput_input")

    print("Selecting Completion Location...")
    select_primefaces_dropdown_by_value(
        "completionLocationInput_input",
        LOCATION_VALUES[offered_location]
    )
    time.sleep(1)

    print("Selecting Program Outcome...")
    select_primefaces_dropdown_by_value(
        "programOutcomeInput_input",
        PROGRAM_OUTCOME_VALUES["Satisfactory Completion"]
    )
    time.sleep(1)

    print("Entering comments...")
    comments = wait.until(
        EC.presence_of_element_located((By.ID, "contactNotesEdit"))
    )
    comments.clear()
    comments.send_keys(f"{csv_row['section_title']} completed on {section_end}.")

    print("Non-Clinical form filled. NOT submitting.")# MATCHING / DECISION ENGINE
# =========================================================
# MAIN
# =========================================================
try:
    print("=== SCRIPT STARTING ===")

    # 🔐 Step 1: Login + land in NICaMS
    login_and_open_nicams()

    print("=== LOGIN/NAVIGATION COMPLETE ===")
    #input("Press Enter to continue to the search stage... ")

    # 🔍 Step 2: Run search + matching logic
    decision, details, candidates = run_trial_search(CSV_RECORD)

    print("\n========== FINAL DECISION ==========")
    print("CSV RECORD:", CSV_RECORD)
    print("DECISION:", decision)
    print("DETAILS:", details)
    print("====================================\n")

    # 🚀 Step 3: If AUTO → open inmate + navigate
    if decision == "AUTO":
        print("\n[ACTION] AUTO match found. Opening inmate record...\n")

        open_selected_candidate(details)

        # Give page time to fully load after click
        time.sleep(2)

        print("\n[ACTION] Navigating to Non-Clinical Program Tracking...\n")

        go_to_non_clinical_program_tracking()

        fill_nonclinical_form(CSV_ROW, offered_location="Community")

        print("Review the filled form. Submit is intentionally disabled.")

        input("Non-Clinical page loaded. Inspect, then press Enter to close...")

    elif decision == "REVIEW":
        print("\n[INFO] REVIEW case. No action taken.")
        input("Inspect candidates manually, then press Enter to close...")

    else:
        print("\n[INFO] NO_MATCH. No action taken.")
        input("No valid candidate. Press Enter to close...")

except Exception as e:
    print("\n[ERROR]", type(e).__name__, e)
    try:
        print("[DEBUG] URL:", driver.current_url)
        print("[DEBUG] Title:", driver.title)
    except Exception:
        print("[DEBUG] Could not read URL/title")

    input("Press Enter to close after reviewing the error...")

finally:
    try:
        driver.quit()
    except Exception:
        pass