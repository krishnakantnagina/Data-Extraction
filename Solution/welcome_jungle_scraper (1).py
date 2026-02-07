import asyncio
import csv
import re
from playwright.async_api import async_playwright

async def scrape_welcome_to_jungle():
    """
    Scrapes job listings from Welcome to the Jungle with specific search criteria.
    Implements pagination, data cleaning, and CSV export.
    """
    
    async with async_playwright() as p:
        # Launch browser in headless mode
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        print("Step 1: Navigating to the website...")
        await page.goto(
            'https://www.welcometothejungle.com/en/jobs?refinementList%5Boffices.country_code%5D%5B%5D=US',
            wait_until='networkidle',
            timeout=60000
        )
        
        # Wait for page to fully load
        await page.wait_for_timeout(5000)
        
        # STEP 1: DISMISS ALL POPUPS FIRST - Try multiple times
        print("Dismissing any popups/modals/overlays...")
        popup_selectors = [
            'button:has-text("Close")',
            'button:has-text("Accept")',
            'button:has-text("Accept all")',
            'button:has-text("Agree")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            'button:has-text("Continue")',
            'button[aria-label*="Close"]',
            'button[aria-label*="close"]',
            'button[aria-label*="Dismiss"]',
            '[data-testid="cookie-banner"] button',
            '[data-testid*="close"]',
            '[data-testid*="dismiss"]',
            '.cookie-banner button',
            '[id*="cookie"] button',
            '[class*="modal"] button',
            '[class*="popup"] button',
            '[class*="overlay"] button',
            '[role="dialog"] button',
            'button[class*="close"]',
            'button[class*="Close"]',
            '[aria-label="Close"]',
            '.close-button',
            '.dismiss-button'
        ]
        
        # Try to close all popups (some sites have multiple)
        popups_closed = 0
        for attempt in range(3):  # Try 3 times to catch stacked popups
            for selector in popup_selectors:
                try:
                    close_btns = page.locator(selector)
                    count = await close_btns.count()
                    for i in range(count):
                        try:
                            btn = close_btns.nth(i)
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                popups_closed += 1
                                print(f"[OK] Closed popup #{popups_closed} using: {selector}")
                                await page.wait_for_timeout(1500)
                        except:
                            continue
                except:
                    continue
            
            # Check if any modals/overlays still visible
            try:
                overlay = page.locator('[role="dialog"], [class*="modal"], [class*="overlay"]').first
                if not await overlay.is_visible(timeout=1000):
                    break
            except:
                break
        
        if popups_closed == 0:
            print("No popups found")
        else:
            print(f"Total popups closed: {popups_closed}")
        
        # Extra wait to ensure page is stable
        await page.wait_for_timeout(2000)
        
        print("\nStep 2 & 3: Searching for 'Business' jobs...")
        
        # Try multiple search input selectors
        search_selectors = [
            'input[type="search"]',
            'input[placeholder*="Search"]',
            'input[placeholder*="search"]',
            'input[name*="query"]',
            'input[name*="search"]',
            '[data-testid*="search"] input',
            '.search-input',
            '#search-input'
        ]
        
        search_input = None
        for selector in search_selectors:
            try:
                elem = page.locator(selector).first
                if await elem.is_visible(timeout=2000):
                    search_input = elem
                    print(f"Found search input using selector: {selector}")
                    break
            except:
                continue
        
        if search_input:
            await search_input.click()
            await page.wait_for_timeout(500)
            await search_input.fill('Business')
            await search_input.press('Enter')
            
            print("Step 4: Waiting for results to load...")
            await page.wait_for_timeout(5000)
        else:
            print("Warning: Could not find search input. Proceeding with current page...")
        
        # Wait for job cards to appear
        print("\nLooking for job cards...")
        await page.wait_for_load_state('networkidle')
        
        all_jobs_data = []
        page_number = 1
        max_pages = 10  # Safety limit
        
        print("\nStep 5: Collecting data from all pages...")
        
        while page_number <= max_pages:
            print(f"\n{'='*60}")
            print(f"SCRAPING PAGE {page_number}")
            print(f"{'='*60}")
            
            # Scroll to load lazy-loaded content
            await auto_scroll(page)
            await page.wait_for_timeout(2000)
            
            # Try multiple selectors for job cards
            card_selectors = [
                '[data-testid*="job-card"]',
                '[data-testid*="search-result"]',
                'li[data-testid]',
                'article',
                '.job-card',
                '[class*="JobCard"]',
                '[class*="job-item"]'
            ]
            
            job_cards = None
            for selector in card_selectors:
                try:
                    cards = await page.locator(selector).all()
                    if len(cards) > 5:  # Reasonable number of job cards
                        job_cards = cards
                        print(f"Found {len(cards)} job cards using selector: {selector}")
                        break
                except:
                    continue
            
            if not job_cards or len(job_cards) == 0:
                print("No job cards found on this page. Ending pagination.")
                break
            
            # Extract data from each job card
            for idx, card in enumerate(job_cards, 1):
                try:
                    job_data = await extract_job_data(card, page)
                    if job_data and job_data.get('Job_Title'):
                        all_jobs_data.append(job_data)
                        print(f"  [{idx}/{len(job_cards)}] [OK] {job_data['Job_Title'][:50]}...")
                    else:
                        print(f"  [{idx}/{len(job_cards)}] [X] Skipped (no title)")
                except Exception as e:
                    print(f"  [{idx}/{len(job_cards)}] ✗ Error: {str(e)[:50]}")
                    continue
            
            print(f"\nExtracted {len(job_cards)} jobs from page {page_number}")
            print(f"Total jobs collected so far: {len(all_jobs_data)}")
            
            # Check for next page button
            has_next = False
            next_selectors = [
                'button:has-text("Next")',
                'a:has-text("Next")',
                '[aria-label*="Next"]',
                'button[aria-label*="next"]',
                '.pagination button:last-child',
                '[data-testid*="next"]',
                '.next-page'
            ]
            
            for selector in next_selectors:
                try:
                    next_btn = page.locator(selector).first
                    if await next_btn.is_visible(timeout=2000):
                        is_enabled = await next_btn.is_enabled()
                        is_disabled = await next_btn.get_attribute('disabled')
                        
                        if is_enabled and not is_disabled:
                            print(f"\n--> Clicking next page using selector: {selector}")
                            await next_btn.click()
                            await page.wait_for_timeout(4000)
                            await page.wait_for_load_state('networkidle')
                            has_next = True
                            break
                except Exception as e:
                    continue
            
            if not has_next:
                print("\n[OK] No more pages available. Pagination complete.")
                break
            
            page_number += 1
        
        await browser.close()
        
        print(f"\n{'='*60}")
        print("Step 6 & 7: Applying data cleaning and storing to CSV...")
        print(f"{'='*60}")
        print(f"Total jobs collected: {len(all_jobs_data)}")
        
        # Apply cleaning rules and save to CSV
        cleaned_data = [clean_job_data(job) for job in all_jobs_data]
        
        # Remove duplicates based on Job_Link
        seen_links = set()
        unique_data = []
        for job in cleaned_data:
            link = job.get('Job_Link', '')
            if link and link not in seen_links:
                seen_links.add(link)
                unique_data.append(job)
            elif not link:
                unique_data.append(job)
        
        print(f"Unique jobs after deduplication: {len(unique_data)}")
        
        save_to_csv(unique_data)
        
        print("\n" + "="*60)
        print("SCRAPING COMPLETED SUCCESSFULLY!")
        print("="*60)
        print(f"CSV file created: welcome_to_jungle_jobs.csv")
        print(f"Total records: {len(unique_data)}")
        print(f"Pages scraped: {page_number}")
        print("="*60)


async def auto_scroll(page):
    """Scroll down the page to load lazy-loaded content"""
    await page.evaluate("""
        async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                let distance = 300;
                let timer = setInterval(() => {
                    let scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;

                    if(totalHeight >= scrollHeight){
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            });
        }
    """)


async def extract_job_data(card, page):
    """
    Extracts data from a single job card.
    Uses multiple selector strategies to find each field.
    """
    job_data = {
        'Job_Title': '',
        'Company_Title': '',
        'Company_Slogan': '',
        'Job_Type': '',
        'Location': '',
        'Work_Location': '',
        'Industry': '',
        'Employes_Count': '',
        'Posted_Ago': '',
        'Job_Link': ''
    }
    
    try:
        # Job Title
        title_selectors = [
            'h3', 'h2', 'h4',
            '[data-testid*="title"]',
            '[class*="title"]',
            '[class*="Title"]',
            'a[href*="/jobs/"]'
        ]
        for selector in title_selectors:
            try:
                elem = card.locator(selector).first
                text = await elem.inner_text(timeout=1000)
                if text and len(text) > 3:
                    job_data['Job_Title'] = text.strip()
                    break
            except:
                continue
        
        # Company Title
        company_selectors = [
            '[data-testid*="company"]',
            '[class*="company"]',
            '[class*="Company"]',
            'a[href*="/companies/"]',
            '[class*="organization"]'
        ]
        for selector in company_selectors:
            try:
                elem = card.locator(selector).first
                text = await elem.inner_text(timeout=1000)
                if text and text != job_data['Job_Title']:
                    job_data['Company_Title'] = text.strip()
                    break
            except:
                continue
        
        # Company Slogan
        slogan_selectors = [
            '[class*="slogan"]',
            '[class*="tagline"]',
            '[class*="description"]',
            '[data-testid*="slogan"]'
        ]
        for selector in slogan_selectors:
            try:
                elem = card.locator(selector).first
                text = await elem.inner_text(timeout=1000)
                if text:
                    job_data['Company_Slogan'] = text.strip()
                    break
            except:
                continue
        
        # Get all text content for parsing
        all_text = await card.inner_text()
        lines = [line.strip() for line in all_text.split('\n') if line.strip()]
        
        # Job Type (Full-time, Part-time, Contract, etc.)
        job_type_keywords = ['full-time', 'part-time', 'contract', 'temporary', 'internship', 'permanent']
        for line in lines:
            if any(keyword in line.lower() for keyword in job_type_keywords):
                job_data['Job_Type'] = line
                break
        
        # Location
        location_selectors = [
            '[data-testid*="location"]',
            '[class*="location"]',
            '[class*="Location"]',
            '[class*="office"]',
            'span:has-text("USA")',
            'span:has-text("United States")'
        ]
        for selector in location_selectors:
            try:
                elem = card.locator(selector).first
                text = await elem.inner_text(timeout=1000)
                if text:
                    job_data['Location'] = text.strip()
                    break
            except:
                continue
        
        # Work Location (Remote, On-site, Hybrid)
        work_mode_keywords = ['remote', 'on-site', 'onsite', 'hybrid', 'office']
        for line in lines:
            if any(keyword in line.lower() for keyword in work_mode_keywords):
                job_data['Work_Location'] = line
                break
        
        # Industry
        industry_selectors = [
            '[class*="industry"]',
            '[class*="sector"]',
            '[data-testid*="industry"]'
        ]
        for selector in industry_selectors:
            try:
                elem = card.locator(selector).first
                text = await elem.inner_text(timeout=1000)
                if text:
                    job_data['Industry'] = text.strip()
                    break
            except:
                continue
        
        # Employee Count
        employee_selectors = [
            '[class*="employee"]',
            '[class*="size"]',
            '[data-testid*="employee"]',
            'span:has-text("employees")'
        ]
        for selector in employee_selectors:
            try:
                elem = card.locator(selector).first
                text = await elem.inner_text(timeout=1000)
                if text and ('employee' in text.lower() or re.search(r'\d+', text)):
                    job_data['Employes_Count'] = text.strip()
                    break
            except:
                continue
        
        # Posted Time
        posted_selectors = [
            '[class*="posted"]',
            '[class*="time"]',
            'time',
            '[datetime]',
            'span:has-text("ago")',
            'span:has-text("day")'
        ]
        for selector in posted_selectors:
            try:
                elem = card.locator(selector).first
                text = await elem.inner_text(timeout=1000)
                if text and ('ago' in text.lower() or 'day' in text.lower() or 'yesterday' in text.lower()):
                    job_data['Posted_Ago'] = text.strip()
                    break
            except:
                continue
        
        # Job Link
        link_selectors = [
            'a[href*="/jobs/"]',
            'a[href*="/job/"]',
            'a[data-testid*="job"]'
        ]
        for selector in link_selectors:
            try:
                elem = card.locator(selector).first
                href = await elem.get_attribute('href', timeout=1000)
                if href:
                    if href.startswith('/'):
                        job_data['Job_Link'] = f"https://www.welcometothejungle.com{href}"
                    elif href.startswith('http'):
                        job_data['Job_Link'] = href
                    break
            except:
                continue
        
        return job_data
        
    except Exception as e:
        print(f"Error in extract_job_data: {e}")
        return job_data


def clean_job_data(job_data):
    """
    Step 6: Apply data cleaning rules.
    (i) Convert "yesterday" to "1 days ago"
    (ii) Convert employee count from "25 employees" to "25"
    """
    cleaned = job_data.copy()
    
    # Rule (i): Convert "yesterday" to "1 days ago"
    if cleaned.get('Posted_Ago'):
        posted_ago = cleaned['Posted_Ago'].strip().lower()
        if 'yesterday' in posted_ago:
            cleaned['Posted_Ago'] = '1 days ago'
    
    # Rule (ii): Convert employee count to number
    if cleaned.get('Employes_Count'):
        employee_text = cleaned['Employes_Count'].strip()
        # Extract number from text like "25 employees" -> "25"
        match = re.search(r'(\d+)', employee_text)
        if match:
            cleaned['Employes_Count'] = match.group(1)
    
    return cleaned


def save_to_csv(data):
    """
    Step 7 & 8: Save data to CSV with exact headers.
    """
    headers = [
        'Job_Title',
        'Company_Title',
        'Company_Slogan',
        'Job_Type',
        'Location',
        'Work_Location',
        'Industry',
        'Employes_Count',
        'Posted_Ago',
        'Job_Link'
    ]
    
    filename = 'welcome_to_jungle_jobs.csv'
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        
        for job in data:
            # Ensure all headers are present
            row = {header: job.get(header, '') for header in headers}
            writer.writerow(row)
    
    print(f"\n[OK] CSV file saved: {filename}")


# Run the scraper
if __name__ == "__main__":
    print("""
========================================================================
                                                                    
   Welcome to the Jungle Job Scraper                                
   ------------------------------------                         
                                                                    
   This script will:                                                
   - Search for 'Business' jobs in the US                           
   - Extract all job data from multiple pages                       
   - Apply data cleaning rules                                      
   - Save to CSV with proper headers                                
                                                                    
========================================================================
    """)
    
    asyncio.run(scrape_welcome_to_jungle())
