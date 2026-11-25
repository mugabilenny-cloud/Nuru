import html, io, os
from datetime import date, datetime

import pandas as pd
import streamlit as st

import db
import importer

st.set_page_config(page_title="Nuru - Find your next opportunity", page_icon="💡", layout="wide")
db.init()

PURPLE = "#6200B3"
CATEGORY_FALLBACK = ["Banks & Finance", "Medical", "Schools & Education", "NGOs & Development",
                     "Engineering & Construction", "ICT & Tech", "Agriculture", "Internships", "Other"]

# ------------------------------------------------------------------ styling
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea {{ font-family: 'Poppins', sans-serif !important; }}
#MainMenu, footer, header[data-testid="stHeader"] {{ display: none; }}
.block-container {{ padding-top: 1rem; max-width: 1180px; }}
.logo {{ font-size: 1.5rem; font-weight: 700; color: {PURPLE}; padding-top: .35rem; }}
.hero {{ background: linear-gradient(135deg,#F3EAFF 0%,#FFFFFF 100%); border-radius: 18px; padding: 3rem 2.5rem 2rem; margin: .8rem 0 1.5rem; }}
.hero h1 {{ font-size: 2.4rem; font-weight: 600; color:#2B2B2B; line-height:1.25; margin:0 0 .4rem; }}
.hero p {{ color:#666; margin:0; }}
.sec-title {{ text-align:center; font-weight:600; font-size:1.8rem; margin:2rem 0 .2rem; }}
.sec-sub {{ text-align:center; color:#666; margin-bottom:1.2rem; }}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.jobcard) {{ background:#F6EFFF; border:1px solid #E6D8F7; border-radius:10px; }}
.jobcard .t {{ font-weight:500; font-size:1.02rem; color:#2B2B2B; }}
.jobcard .m {{ font-size:.78rem; color:#777; margin:.15rem 0; }}
.jobcard .c {{ font-size:.85rem; color:#444; margin-top:.4rem; }}
.badge {{ display:inline-block; font-size:.66rem; font-weight:600; padding:1px 8px; border-radius:4px; margin-right:6px; letter-spacing:.3px; }}
.b-Full-time {{ background:#E6D8F7; color:{PURPLE}; }} .b-Part-time {{ background:#D8F5DF; color:#13813A; }}
.b-Internship {{ background:#FFF1D1; color:#9A6200; }} .b-Contract {{ background:#D9ECFF; color:#0B5CAD; }}
.b-Scholarship {{ background:#FFE0EC; color:#B0124F; }} .b-closed {{ background:#FDE0E0; color:#B00020; }}
.chip {{ display:inline-block; background:#fff; border:1px solid #E6D8F7; border-radius:20px; padding:4px 14px; margin:3px; font-size:.85rem; color:#444; }}
.stButton > button, .stFormSubmitButton > button, .stLinkButton > a {{ border-radius:6px; font-weight:500; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{ background:{PURPLE}; border-color:{PURPLE}; color:#fff; }}
.stButton > button[kind="secondary"] {{ border-color:{PURPLE}; color:{PURPLE}; background:#fff; }}
.footer {{ background:#F3EAFF; border-radius:14px; padding:1.6rem 2rem; margin-top:3rem; color:#555; font-size:.85rem; }}
</style>""", unsafe_allow_html=True)

# ------------------------------------------------------------------ state / auth helpers
ss = st.session_state
ss.setdefault("page", "Home")
ss.setdefault("user", None)
ss.setdefault("limit", 8)


def go(page):
    ss.page = page


def admin_emails():
    raw = os.environ.get("NURU_ADMIN_EMAILS", "")
    try:
        raw = raw or st.secrets.get("ADMIN_EMAILS", "")
    except Exception:
        pass
    return {e.strip().lower() for e in str(raw).split(",") if e.strip()}


def is_admin():
    return bool(ss.user and ss.user["role"] == "admin")


def login_user(u):
    if u["email"] in admin_emails() and u["role"] != "admin":
        db.set_role(u["email"], "admin")
        u["role"] = "admin"
    ss.user = {k: u[k] for k in ("email", "name", "role")}


def esc(x):
    return html.escape(str(x or ""))


def fmt_date(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        return ""


def is_closed(row):
    if row["status"] == "closed":
        return True
    d = row["deadline"]
    return bool(d) and not pd.isna(d) and d < date.today().isoformat()


def salary_text(row):
    lo, hi, cur = row["salary_min"], row["salary_max"], row["currency"] or "UGX"
    lo = None if pd.isna(lo) else lo
    hi = None if pd.isna(hi) else hi
    if lo and hi:
        return f"{cur} {lo:,.0f} - {hi:,.0f}"
    if lo or hi:
        return f"{cur} {(lo or hi):,.0f}"
    return ""


# ------------------------------------------------------------------ shared UI
def navbar():
    items = ["Home", "Find Jobs", "Post a Job", "Dashboard", "About"]
    cols = st.columns([1.5] + [1] * len(items) + [1.1, 1.1])
    cols[0].markdown('<div class="logo">💡 Nuru</div>', unsafe_allow_html=True)
    for i, p in enumerate(items, start=1):
        cols[i].button(p, key=f"nav_{p}", on_click=go, args=(p,), use_container_width=True,
                       type="primary" if ss.page == p else "secondary")
    if ss.user:
        cols[-2].caption(f"Hi, {ss.user['name'].split()[0]}")
        if cols[-1].button("Logout", use_container_width=True):
            ss.user = None
            ss.page = "Home"
            st.rerun()
    else:
        cols[-2].button("Register", key="nav_reg", on_click=go, args=("Register",), use_container_width=True)
        cols[-1].button("Login", key="nav_login", on_click=go, args=("Login",), use_container_width=True, type="primary")
    st.divider()


def footer():
    st.markdown("""<div class="footer"><b style="color:#6200B3">💡 Nuru</b> - jobs, internships and scholarships for Ugandans.<br>
    Kampala, Uganda &nbsp;|&nbsp; Always confirm deadlines and requirements on the official listing before applying.<br>
    © 2026 Nuru. All rights reserved.</div>""", unsafe_allow_html=True)


def card_html(r):
    closed = is_closed(r)
    badges = f'<span class="badge b-{esc(r["job_type"])}">{esc(str(r["job_type"]).upper())}</span>'
    if closed:
        badges += '<span class="badge b-closed">CLOSED</span>'
    sal = salary_text(r)
    meta = f"Salary: {esc(sal)}" if sal else (f"Closes {fmt_date(r['deadline'])}" if r["deadline"] else "")
    org = esc(r["company"]) or ("Scholarship" if r["kind"] == "Scholarship" else "Employer")
    app = f" &nbsp;·&nbsp; {int(r['applicants'])} applicant(s)" if r["applicants"] else ""
    return (f'<div class="jobcard"><div class="t">{esc(r["title"])}</div>'
            f'<div class="m">{badges}{meta}</div>'
            f'<div class="c"><b>{org}</b></div>'
            f'<div class="m">📍 {esc(r["location"])} &nbsp;·&nbsp; {esc(r["category"])}{app}</div></div>')


@st.dialog("Opportunity details", width="large")
def detail_dialog(lid):
    r = db.get_listing(lid)
    if not r:
        st.error("Listing not found.")
        return
    row = pd.Series(r)
    row["applicants"] = 0
    st.markdown(f"### {r['title']}")
    st.markdown(card_html(row), unsafe_allow_html=True)
    st.write(r["description"] or "No description provided.")
    if r["deadline"]:
        st.caption(f"Deadline: {fmt_date(r['deadline'])}")
    if is_closed(row):
        st.warning("This listing is closed or past its deadline. Check the official page in case it was extended.")
    if r["url"]:
        st.link_button("Open official listing / apply ↗", r["url"], type="primary")
    if r["apply_email"]:
        st.markdown(f"Or email your CV to **{r['apply_email']}**")
    if r["source"] == "form" and r["status"] == "active":
        st.markdown("#### Apply on Nuru")
        u = ss.user or {}
        with st.form(f"apply_{lid}", clear_on_submit=True):
            name = st.text_input("Full name", value=u.get("name", ""))
            email = st.text_input("Email", value=u.get("email", ""))
            phone = st.text_input("Phone")
            msg = st.text_area("Cover note")
            if st.form_submit_button("Submit application", type="primary"):
                if not (name.strip() and "@" in email):
                    st.error("Name and a valid email are required.")
                else:
                    db.add_application(lid, name, email, phone, msg)
                    st.success("Application sent. The employer will see it on their dashboard.")


def listing_grid(df, ctx, ncols=2):
    for i in range(0, len(df), ncols):
        cols = st.columns(ncols)
        for col, (_, r) in zip(cols, df.iloc[i:i + ncols].iterrows()):
            with col, st.container(border=True):
                st.markdown(card_html(r), unsafe_allow_html=True)
                b1, b2 = st.columns(2)
                if b1.button("View details", key=f"v_{ctx}_{r['id']}", use_container_width=True):
                    detail_dialog(int(r["id"]))
                if b2.button("Apply now", key=f"a_{ctx}_{r['id']}", use_container_width=True, type="primary"):
                    detail_dialog(int(r["id"]))


def search_to_jobs():
    ss.page = "Find Jobs"
    ss.limit = 8


# ------------------------------------------------------------------ pages
def page_home():
    df = db.listings_df()
    jobs = df[df.kind == "Job"]
    st.markdown("""<div class="hero"><h1>Find an opportunity that fits<br>your interests and skills</h1>
    <p>Jobs, internships and scholarships in Uganda and beyond, all in one place.</p></div>""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([3, 2, 1])
    c1.text_input("Job title, keyword...", key="q", label_visibility="collapsed", placeholder="🔍  Job title, keyword...")
    c2.text_input("Location", key="loc", label_visibility="collapsed", placeholder="📍  Location")
    c3.button("Find Job", type="primary", use_container_width=True, on_click=search_to_jobs)
    st.caption("Suggestion: Accountant, Nurse, Engineer, Scholarship, Internship")

    st.markdown('<div class="sec-title">Featured Jobs</div><div class="sec-sub">Choose from top employers and apply.</div>',
                unsafe_allow_html=True)
    live = jobs[~jobs.apply(is_closed, axis=1)] if len(jobs) else jobs
    feat = (live if len(live) >= 3 else jobs).head(3)
    if len(feat):
        listing_grid(feat, "home", ncols=3)
    st.button("View all", on_click=search_to_jobs)

    top = jobs[jobs.company != ""].company.value_counts().head(10).index.tolist()
    if top:
        st.markdown('<div class="sec-sub" style="margin-top:2rem">Top organisations hiring now</div>', unsafe_allow_html=True)
        st.markdown('<div style="text-align:center">' + "".join(f'<span class="chip">{esc(t)}</span>' for t in top) + "</div>",
                    unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("Jobs & internships", len(jobs))
    m2.metric("Scholarships", int((df.kind == "Scholarship").sum()))
    m3.metric("Organisations", int(df.company.replace("", pd.NA).nunique()))
    footer()


def page_find():
    df = db.listings_df()
    st.markdown("## Job Search")
    c1, c2, c3 = st.columns([3, 2, 1])
    q = c1.text_input("Job title / keyword", key="q", placeholder="🔍  Job title, keyword...", label_visibility="collapsed")
    loc = c2.text_input("Location", key="loc", placeholder="📍  Location", label_visibility="collapsed")
    c3.button("Search", type="primary", use_container_width=True)

    left, right = st.columns([1, 3])
    with left:
        h1, h2 = st.columns([1, 1])
        h1.markdown("**Filter**")
        if h2.button("Clear all"):
            for k in ("q", "loc", "f_kind", "f_type", "f_mode", "f_cat", "f_hide"):
                ss.pop(k, None)
            st.rerun()
        kind = st.radio("Show", ["All", "Job", "Scholarship"], key="f_kind", horizontal=True,
                        format_func=lambda x: {"All": "All", "Job": "Jobs", "Scholarship": "Scholarships"}[x])
        base = df if kind == "All" else df[df.kind == kind]
        jt = st.multiselect("Job type", sorted(base.job_type.unique()), key="f_type")
        wm = st.multiselect("Work mode", [m for m in importer.WORK_MODES if m in set(base.work_mode)], key="f_mode")
        cats = base.category.value_counts()
        cat = st.multiselect("Category", list(cats.index), key="f_cat", format_func=lambda c: f"{c} ({cats[c]})")
        hide = st.checkbox("Hide closed / expired", key="f_hide")
        with st.expander("Salary range (UGX)"):
            smin = st.number_input("Min", min_value=0, step=100000, value=0)
            smax = st.number_input("Max", min_value=0, step=100000, value=0)

    f = base
    if q:
        blob = (f.title + " " + f.company + " " + f.description + " " + f.category).str.lower()
        for w in q.lower().split():
            f = f[blob.loc[f.index].str.contains(w, regex=False)]
    if loc:
        f = f[f.location.str.lower().str.contains(loc.lower(), regex=False)]
    if jt:
        f = f[f.job_type.isin(jt)]
    if wm:
        f = f[f.work_mode.isin(wm)]
    if cat:
        f = f[f.category.isin(cat)]
    if hide and len(f):
        f = f[~f.apply(is_closed, axis=1)]
    if smin:
        f = f[f.salary_max.fillna(f.salary_min).fillna(0) >= smin]
    if smax:
        f = f[f.salary_min.fillna(f.salary_max).fillna(0).le(smax) | f.salary_min.isna() & f.salary_max.isna()]

    with right:
        t1, t2 = st.columns([3, 1])
        t1.markdown(f"### All Listings ({len(f)})")
        sort = t2.selectbox("Sort", ["Latest", "Deadline soon", "Most applied"], label_visibility="collapsed")
        if sort == "Deadline soon":
            f = f.assign(_d=f.deadline.fillna("9999")).sort_values("_d")
        elif sort == "Most applied":
            f = f.sort_values("applicants", ascending=False)
        if f.empty:
            st.info("No listings match your filters.")
        else:
            listing_grid(f.head(ss.limit), "find")
            if len(f) > ss.limit:
                st.button("View more", on_click=lambda: ss.update(limit=ss.limit + 8))
    footer()


def page_post():
    st.markdown("## Post a job")
    st.caption("Find the best talent for your company")
    if not ss.user:
        st.info("Please log in or register as an employer to post a job.")
        st.button("Login", on_click=go, args=("Login",), type="primary")
        return
    existing = db.listings_df()
    cats = sorted(set(existing.category) | set(CATEGORY_FALLBACK))
    with st.form("post_job", clear_on_submit=True):
        title = st.text_input("Job title*", placeholder="e.g. Senior Accountant")
        company = st.text_input("Company / organisation*", value=ss.user["name"])
        c1, c2 = st.columns(2)
        category = c1.selectbox("Category*", cats)
        job_type = c2.selectbox("Job type", ["Full-time", "Part-time", "Internship", "Contract"])
        c3, c4 = st.columns(2)
        work_mode = c3.selectbox("Work mode", importer.WORK_MODES)
        location = c4.text_input("Location*", value="Kampala")
        s1, s2, s3 = st.columns(3)
        currency = s1.selectbox("Currency", ["UGX", "USD", "KES", "EUR"])
        smin = s2.number_input("Min salary", min_value=0, step=100000)
        smax = s3.number_input("Max salary", min_value=0, step=100000)
        d1, d2 = st.columns(2)
        deadline = d1.date_input("Application deadline", value=None, min_value=date.today())
        apply_email = d2.text_input("Application email or URL (optional)")
        desc = st.text_area("Job description*", height=180, placeholder="Responsibilities, requirements, how to apply...")
        ok = st.form_submit_button("Post Job", type="primary")
    if ok:
        if not (title.strip() and company.strip() and location.strip() and desc.strip()):
            st.error("Title, company, location and description are required.")
        else:
            is_url = apply_email.strip().lower().startswith("http")
            db.post_job(dict(kind="Job", title=title.strip(), company=company.strip(), category=category,
                             job_type=job_type, work_mode=work_mode, location=location.strip(),
                             salary_min=smin or None, salary_max=smax or None, currency=currency,
                             deadline=deadline.isoformat() if deadline else None, description=desc.strip(),
                             url=apply_email.strip() if is_url else "",
                             apply_email="" if is_url else apply_email.strip()), ss.user["email"])
            st.success("Job posted. It is now live on Find Jobs and listed on your dashboard.")
            st.button("Go to dashboard", on_click=go, args=("Dashboard",), type="primary")


def bulk_upload_ui(owner):
    st.markdown("#### Bulk upload from Excel / CSV")
    st.caption("Use the same layout as hub_repo.xlsx: **path, title, url, details**. "
               "Duplicates (same URL) are skipped automatically.")
    tpl = pd.DataFrame([{"path": "Jobs/Banks & Finance", "title": "Example Bank - Credit Officer",
                         "url": "https://example.com/job/1",
                         "details": "Kampala. Closes 30 Dec 2026. Degree in Finance, 2 yrs experience. Email CV to hr@example.com"}])
    buf = io.BytesIO()
    tpl.to_excel(buf, index=False)
    st.download_button("⬇ Download template", buf.getvalue(), "nuru_template.xlsx")
    up = st.file_uploader("Upload .xlsx or .csv", type=["xlsx", "csv"])
    if up:
        try:
            items = importer.parse_dataframe(importer.read_file(up))
        except Exception as e:
            st.error(f"Could not read file: {e}")
            return
        prev = pd.DataFrame(items)[["kind", "title", "company", "category", "location", "deadline"]]
        st.write(f"{len(items)} rows parsed. Preview:")
        st.dataframe(prev, use_container_width=True, hide_index=True)
        if st.button(f"Import {len(items)} listings", type="primary"):
            added, skipped = db.bulk_add(items, source="excel", owner=owner)
            st.success(f"Added {added}. Skipped {skipped} duplicate(s).")
            st.rerun()


def page_dashboard():
    st.markdown("## Dashboard")
    if not ss.user:
        st.info("Log in to see your dashboard.")
        st.button("Login", on_click=go, args=("Login",), type="primary")
        return
    admin = is_admin()
    owner = ss.user["email"]
    scope_all = admin and st.toggle("Admin view: show every listing", value=True)
    mine = db.listings_df(None if scope_all else owner)
    apps = db.applications_df(None if scope_all else owner)
    m1, m2, m3 = st.columns(3)
    m1.metric("Total listings", len(mine))
    m2.metric("Active", int((~mine.apply(is_closed, axis=1)).sum()) if len(mine) else 0)
    m3.metric("Applications received", len(apps))

    t1, t2, t3 = st.tabs(["📋 Posted jobs", "📨 Applications", "⬆ Bulk upload & export"])
    with t1:
        if mine.empty:
            st.info("Nothing posted yet.")
            st.button("Post your first job", on_click=go, args=("Post a Job",), type="primary")
        else:
            q = st.text_input("Filter this list", placeholder="Search title, company, category...")
            lst = mine
            if q:
                blob = (mine.title + " " + mine.company + " " + mine.category).str.lower()
                lst = mine[blob.str.contains(q.lower(), regex=False)]
            page_size = 15
            pages = max(1, -(-len(lst) // page_size))
            pg = st.number_input("Page", 1, pages, 1) if pages > 1 else 1
            for _, r in lst.iloc[(pg - 1) * page_size: pg * page_size].iterrows():
                with st.container(border=True):
                    a, b, c, d = st.columns([5, 1.4, 1.2, 1.2])
                    a.markdown(card_html(r), unsafe_allow_html=True)
                    a.caption(f"Posted {r['created_at'][:10]} · {r['source']}")
                    b.metric("Applicants", int(r["applicants"]))
                    if r["status"] == "active":
                        c.button("Close", key=f"cl{r['id']}", on_click=db.set_status, args=(int(r["id"]), "closed"),
                                 use_container_width=True)
                    else:
                        c.button("Reopen", key=f"re{r['id']}", on_click=db.set_status, args=(int(r["id"]), "active"),
                                 use_container_width=True)
                    d.button("Delete", key=f"de{r['id']}", on_click=db.delete_listing, args=(int(r["id"]),),
                             use_container_width=True)
    with t2:
        if apps.empty:
            st.info("No applications yet.")
        else:
            st.dataframe(apps, use_container_width=True, hide_index=True)
    with t3:
        bulk_upload_ui(owner)
        st.divider()
        st.markdown("#### Export (backup)")
        out = mine.drop(columns=["dedupe_key"], errors="ignore")
        buf = io.BytesIO()
        out.to_excel(buf, index=False)
        st.download_button("⬇ Download listings (.xlsx)", buf.getvalue(), "nuru_listings.xlsx")


def auth_form(register):
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(f"## {'Create your account' if register else 'Login to your account'}")
        with st.form("auth"):
            if register:
                name = st.text_input("Full name*")
            email = st.text_input("Email ID*")
            if register:
                phone = st.text_input("Mobile number*", placeholder="+256 ...")
                role = st.radio("I am a", ["candidate", "employer"], horizontal=True,
                                format_func=lambda x: x.title())
            pw = st.text_input("Password*" + (" (min 6 characters)" if register else ""), type="password")
            ok = st.form_submit_button("Register now" if register else "Login", type="primary", use_container_width=True)
        if ok:
            if register:
                if not (name.strip() and "@" in email and phone.strip() and len(pw) >= 6):
                    st.error("Fill every field. Password needs at least 6 characters.")
                else:
                    role = "admin" if email.strip().lower() in admin_emails() else role
                    if db.create_user(email, name, phone, pw, role):
                        login_user(db.verify_user(email, pw))
                        ss.page = "Dashboard"
                        st.rerun()
                    else:
                        st.error("That email is already registered.")
            else:
                u = db.verify_user(email, pw)
                if u:
                    login_user(u)
                    ss.page = "Dashboard"
                    st.rerun()
                else:
                    st.error("Wrong email or password.")
        if register:
            st.button("Already have an account? Login", on_click=go, args=("Login",))
        else:
            st.button("Don't have an account? Register", on_click=go, args=("Register",))


def page_about():
    st.markdown("## About Nuru")
    st.write("Nuru (Luganda/Swahili for *light*) helps Ugandans find jobs, internships and scholarships in one place, "
             "and lets employers post vacancies and manage applications.")
    st.write("**Contact:** Kampala, Uganda")
    footer()


navbar()
{"Home": page_home, "Find Jobs": page_find, "Post a Job": page_post, "Dashboard": page_dashboard,
 "About": page_about, "Login": lambda: auth_form(False), "Register": lambda: auth_form(True)}[ss.page]()
