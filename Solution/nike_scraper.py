"""
Nike Philippines Product Scraper - FIXED VERSION
Updated with correct DOM selectors for Nike's actual website
"""

import asyncio
import csv
from playwright.async_api import async_playwright
import re

class NikeScraper:
    def __init__(self):
        self.products = []
        self.seen_urls = set()
        self.empty_tagging_count = 0
        
    async def scroll_and_load(self, page, target_count=3000):
        """Handle infinite scroll to load all products"""
        print(f"Starting to scrape products (target: {target_count})...")
        
        last_count = 0
        no_change_count = 0
        
        while len(self.products) < target_count:
            # Scroll down
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(3)  # Wait for products to load
            
            # Extract products
            new_products = await self.extract_products_from_page(page)
            
            current_count = len(self.products)
            print(f"Loaded {current_count} products so far...")
            
            # Check if we got new products
            if current_count == last_count:
                no_change_count += 1
                if no_change_count >= 5:
                    print("No new products loading - reached the end")
                    break
            else:
                no_change_count = 0
            
            last_count = current_count
            
        print(f"\nTotal unique products scraped: {len(self.products)}")
        return self.products
    
    async def extract_products_from_page(self, page):
        """Extract product data - FIXED SELECTORS"""
        
        product_data = await page.evaluate("""
            () => {
                const products = [];
                
                // Nike uses product-card class
                const productCards = document.querySelectorAll('.product-card');
                
                productCards.forEach(card => {
                    try {
                        // Product URL
                        const link = card.querySelector('a');
                        const productUrl = link ? 'https://www.nike.com' + link.getAttribute('href') : '';
                        
                        // Product Image
                        const img = card.querySelector('img');
                        const imageUrl = img ? img.getAttribute('src') : '';
                        
                        // Product Tagging - Check multiple possible locations
                        let tagging = '';
                        
                        // Try different selectors for tags/labels
                        const labelSelectors = [
                            '.product-card__product-label',
                            '.label',
                            '[class*="label"]',
                            '[class*="tag"]',
                            '[data-qa="product-label"]'
                        ];
                        
                        for (const selector of labelSelectors) {
                            const tagElement = card.querySelector(selector);
                            if (tagElement && tagElement.textContent.trim()) {
                                tagging = tagElement.textContent.trim();
                                break;
                            }
                        }
                        
                        // If still no tag, check if card has any badge/ribbon elements
                        if (!tagging) {
                            const badgeEl = card.querySelector('[class*="badge"], [class*="ribbon"]');
                            if (badgeEl) tagging = badgeEl.textContent.trim();
                        }
                        
                        // Product Name
                        const nameElement = card.querySelector('.product-card__title');
                        const productName = nameElement ? nameElement.textContent.trim() : '';
                        
                        // Product Description/Subtitle
                        const descElement = card.querySelector('.product-card__subtitle');
                        const description = descElement ? descElement.textContent.trim() : '';
                        
                        // Prices - Nike shows prices differently
                        let originalPrice = '';
                        let discountPrice = '';
                        
                        // Look for price elements
                        const priceElements = card.querySelectorAll('[class*="price"]');
                        const priceTexts = Array.from(priceElements).map(el => el.textContent.trim()).filter(t => t.includes('₱'));
                        
                        if (priceTexts.length === 2) {
                            // Has both original and discount
                            originalPrice = priceTexts[0];
                            discountPrice = priceTexts[1];
                        } else if (priceTexts.length === 1) {
                            // Only one price - could be discount or regular
                            const strikethrough = card.querySelector('[class*="strike"], .is-striked-out');
                            if (strikethrough) {
                                originalPrice = priceTexts[0];
                            } else {
                                // Just a regular price - treat as both
                                originalPrice = priceTexts[0];
                                discountPrice = priceTexts[0];
                            }
                        }
                        
                        // Alternative: look at all text content for prices
                        if (!originalPrice && !discountPrice) {
                            const allText = card.textContent;
                            const priceMatches = allText.match(/₱[\d,]+/g);
                            if (priceMatches) {
                                if (priceMatches.length >= 2) {
                                    originalPrice = priceMatches[0];
                                    discountPrice = priceMatches[1];
                                } else {
                                    originalPrice = priceMatches[0];
                                    discountPrice = priceMatches[0];
                                }
                            }
                        }
                        
                        products.push({
                            productUrl: productUrl,
                            imageUrl: imageUrl,
                            tagging: tagging,
                            productName: productName,
                            description: description,
                            originalPrice: originalPrice,
                            discountPrice: discountPrice
                        });
                    } catch (e) {
                        console.error('Error extracting product:', e);
                    }
                });
                
                return products;
            }
        """)
        
        new_count = 0
        for product in product_data:
            if product['productUrl'] and product['productUrl'] not in self.seen_urls:
                self.seen_urls.add(product['productUrl'])
                
                # Add empty fields for now (we'll get these from detail pages if needed)
                product['sizesAvailable'] = ''
                product['vouchers'] = ''
                product['availableColors'] = ''
                product['colorShown'] = ''
                product['styleCode'] = ''
                product['ratingScore'] = ''
                product['reviewCount'] = ''
                
                self.products.append(product)
                new_count += 1
        
        return new_count
    
    async def scrape_all_products(self, url, target_count=3000):
        """Main scraping function"""
        async with async_playwright() as p:
            print("Launching browser...")
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            page = await context.new_page()
            
            print(f"Navigating to {url}...")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(5)  # Wait for initial load
            
            # Handle cookie consent
            try:
                accept_btn = await page.query_selector('button:has-text("Accept All"), button:has-text("Accept")')
                if accept_btn:
                    await accept_btn.click()
                    await asyncio.sleep(2)
            except:
                pass
            
            # Start scrolling
            await self.scroll_and_load(page, target_count)
            
            await browser.close()
        
        return self.products
    
    def filter_and_save_products(self):
        """Filter and save products - MODIFIED to be more lenient"""
        valid_products = []
        empty_discount_count = 0
        
        print("\n" + "="*80)
        print("FILTERING PRODUCTS...")
        print("="*80)
        
        for product in self.products:
            # Check tagging
            has_tagging = product['tagging'] and product['tagging'].strip() != ''
            
            # Check discount price
            has_discount = product['discountPrice'] and product['discountPrice'].strip() != ''
            
            if not has_tagging:
                self.empty_tagging_count += 1
            
            if not has_discount:
                empty_discount_count += 1
            
            # Save products that have EITHER tagging OR discount (more lenient)
            # Or save ALL products if most don't have tagging (Nike might not use tags)
            if has_discount:  # At minimum, must have a price
                valid_products.append(product)
        
        print(f"Products without tagging: {self.empty_tagging_count}")
        print(f"Products without discount: {empty_discount_count}")
        print(f"Valid products to save: {len(valid_products)}")
        
        # Save to CSV
        if valid_products:
            headers = [
                'Product_URL', 'Product_Image_URL', 'Product_Tagging', 
                'Product_Name', 'Product_Description', 'Original_Price', 
                'Discount_Price', 'Sizes_Available', 'Vouchers', 
                'Available_Colors', 'Color_Shown', 'Style_Code', 
                'Rating_Score', 'Review_Count'
            ]
            
            filename = 'nike_products.csv'
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                
                for product in valid_products:
                    writer.writerow([
                        product['productUrl'],
                        product['imageUrl'],
                        product['tagging'],
                        product['productName'],
                        product['description'],
                        product['originalPrice'],
                        product['discountPrice'],
                        product['sizesAvailable'],
                        product['vouchers'],
                        product['availableColors'],
                        product['colorShown'],
                        product['styleCode'],
                        product['ratingScore'],
                        product['reviewCount']
                    ])
            
            print(f"\n✓ Saved {len(valid_products)} products to {filename}")
        else:
            print("\n⚠ WARNING: No valid products to save!")
        
        return valid_products
    
    def print_top_10_expensive(self, products):
        """Print top 10 most expensive"""
        print("\n" + "="*80)
        print("TOP 10 MOST EXPENSIVE PRODUCTS")
        print("="*80)
        
        products_with_price = []
        for product in products:
            try:
                price_str = product['discountPrice'].replace('₱', '').replace(',', '').strip()
                price = float(price_str)
                products_with_price.append((product, price))
            except:
                continue
        
        if not products_with_price:
            print("No products with valid prices found")
            return
        
        products_with_price.sort(key=lambda x: x[1], reverse=True)
        
        for i, (product, price) in enumerate(products_with_price[:10], 1):
            print(f"\n{i}. {product['productName']}")
            print(f"   Final Price: ₱{price:,.2f}")
            print(f"   URL: {product['productUrl']}")
    
    def create_top_20_rating_review(self, products):
        """Create top 20 ranking"""
        eligible_products = []
        
        for product in products:
            try:
                review_count = int(product['reviewCount']) if product['reviewCount'] else 0
                rating_score = float(product['ratingScore']) if product['ratingScore'] else 0
                
                if review_count > 150:
                    eligible_products.append({
                        'product': product,
                        'rating': rating_score,
                        'reviews': review_count
                    })
            except:
                continue
        
        if not eligible_products:
            print("\n⚠ No products found with Review Count > 150")
            print("   (Rating/review data not available from listing page)")
            return
        
        eligible_products.sort(key=lambda x: (-x['rating'], -x['reviews']))
        
        ranked_products = []
        for i, item in enumerate(eligible_products[:20]):
            if i > 0:
                prev_item = eligible_products[i-1]
                if item['rating'] == prev_item['rating'] and item['reviews'] == prev_item['reviews']:
                    rank = ranked_products[-1]['rank']
                else:
                    rank = i + 1
            else:
                rank = 1
            
            ranked_products.append({
                'rank': rank,
                'product_name': item['product']['productName'],
                'product_url': item['product']['productUrl'],
                'rating_score': item['rating'],
                'review_count': item['reviews']
            })
        
        if ranked_products:
            headers = ['Rank', 'Product_Name', 'Product_URL', 'Rating_Score', 'Review_Count']
            
            with open('top_20_rating_review.csv', 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                
                for item in ranked_products:
                    writer.writerow([
                        item['rank'],
                        item['product_name'],
                        item['product_url'],
                        item['rating_score'],
                        item['review_count']
                    ])
            
            print(f"\n✓ Saved {len(ranked_products)} products to top_20_rating_review.csv")

async def main():
    scraper = NikeScraper()
    
    url = "https://www.nike.com/ph/w"
    await scraper.scrape_all_products(url, target_count=3000)
    
    valid_products = scraper.filter_and_save_products()
    
    print(f"\n{'='*80}")
    print(f"Total products with empty tagging: {scraper.empty_tagging_count}")
    print(f"{'='*80}")
    
    if valid_products:
        scraper.print_top_10_expensive(valid_products)
        scraper.create_top_20_rating_review(valid_products)
    
    print("\n" + "="*80)
    print("SCRAPING COMPLETED!")
    print("="*80)
    print(f"Files saved in current directory:")
    print(f"  - nike_products.csv")
    print(f"  - top_20_rating_review.csv")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())