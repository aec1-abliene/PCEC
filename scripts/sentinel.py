import os
import sys
import json
import time
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime

# Configuration
API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_FILE = "blog.json"

if not API_KEY:
    print("CRITICAL: GEMINI_API_KEY environment variable not found. Sentinel halting.")
    exit(1)

# PCEC Intelligence Sources
SOURCES = [
    {"name": "Utility Dive", "rss": "https://www.utilitydive.com/feeds/news/"},
    {"name": "Power Magazine", "rss": "https://www.powermag.com/feed/"},
    {"name": "Consulting-Specifying Engineer", "rss": "https://www.csemag.com/feed/"},
    {"name": "EC&M", "rss": "https://www.ecmweb.com/rss/articles"},
    {"name": "Electrical Contractor", "rss": "https://www.ecmag.com/rss.xml"}
]

def load_blog():
    if os.path.exists(BLOG_FILE):
        try:
            with open(BLOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except UnicodeDecodeError:
            print("UnicodeDecodeError encountered. Attempting to load as cp1252...")
            try:
                with open(BLOG_FILE, 'r', encoding='cp1252') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Failed to load blog as cp1252: {e}")
                return []
        except json.JSONDecodeError:
            return []
    return []

def save_blog(data):
    with open(BLOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def is_duplicate(title, blog_data):
    for post in blog_data[:20]:
        if title[:20].lower() in post.get("original_title", "").lower() or title[:20].lower() in post.get("title", "").lower():
            return True
    return False

def prune_images(blog_data):
    MAX_IMAGES = 20
    for idx, post in enumerate(blog_data):
        image_path = post.get("image", "")
        if idx >= MAX_IMAGES:
            if image_path.startswith("images/blog/"):
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                        print(f"Pruned old image to save space: {image_path}")
                    except Exception as e:
                        print(f"Error removing {image_path}: {e}")
            post["image"] = "assets/logo.png"

def get_latest_stories():
    blog_data = load_blog()
    found_stories = []
    
    for source in SOURCES:
        print(f"Scanning {source['name']}...")
        try:
            feed = feedparser.parse(source['rss'])
            if not feed.entries:
                continue
                
            for latest in feed.entries[:3]:
                title = latest.title
                link = latest.link
                
                if is_duplicate(title, blog_data) or is_duplicate(title, found_stories):
                    continue
                    
                content = latest.get('description', '')
                soup = BeautifulSoup(content, 'html.parser')
                clean_content = soup.get_text(separator=' ', strip=True)
                
                if len(clean_content) > 50:
                    found_stories.append({
                        "source": source['name'],
                        "original_title": title,
                        "link": link,
                        "content": clean_content[:1500]
                    })
                    break 
        except Exception as e:
            print(f"Error scanning {source['name']}: {e}")
            
    return found_stories

def rewrite_story(raw_story):
    print("Processing: Artificial Intelligence")
    prompt = f"""
    You are the Chief Electrical Engineer and Content Strategist for 'Parker County Electrical Contractors' (PCEC).
    You are writing a blog post based on the following industry news.
    Tone: Highly professional, industrial, authoritative, and focused on operational resilience.
    Focus on how this impacts commercial and industrial electrical infrastructure in Texas.
    
    Source Article Title: {raw_story['original_title']}
    Source Snippet: {raw_story['content']}
    
    Use your vast knowledge base to extrapolate the context of the snippet and write a full briefing.
    
    Output your response strictly in the following JSON format, do not include any markdown blocks or other text:
    {{
        "title": "Your new highly engaging, authoritative title",
        "category": "Industrial Tech",
        "summary": "A 1-2 sentence punchy summary",
        "content": "The full rewritten article, at least 2 paragraphs. Use HTML <br><br> tags for paragraph breaks instead of newlines.",
        "image_prompt": "A 5-8 word descriptive prompt for an AI image generator (e.g., 'industrial power grid dark neon', 'commercial electrical switchgear futuristic')"
    }}
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts":[{"text": prompt}]}]
    }
    
    try:
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        res.raise_for_status()
        data = res.json()
        result_text = data['candidates'][0]['content']['parts'][0]['text']
        result_text = result_text.replace('```json', '').replace('```', '').strip()
        return json.loads(result_text)
    except Exception as e:
        print(f"Error generating content with Gemini REST API: {e}")
        if 'res' in locals():
            print(f"Response dump: {res.text}")
        return None

def run_sentinel():
    print("PCEC Sentinel Initiated.")
    
    stories = get_latest_stories()
    if not stories:
        print("No fresh stories found today. Sentinel standing down.")
        return
        
    blog_data = load_blog()
    
    story = stories[0]
    print(f"Processing story: {story['original_title']}")
    
    new_post = rewrite_story(story)
    if new_post:
        new_id = 1
        if blog_data:
            new_id = max([p.get('id', 0) for p in blog_data]) + 1
            
        today_str = datetime.now().strftime("%b %d, %Y")
        
        content = new_post.get("content", "").replace('<br><br>', '\n\n')
        
        import urllib.parse
        image_prompt = new_post.get("image_prompt", "industrial electrical power grid futuristic cobalt blue yellow accent")
        # Ensure it has the color scheme
        if "blue" not in image_prompt.lower():
            image_prompt += " cobalt blue accents"
            
        encoded_prompt = urllib.parse.quote(image_prompt)
        pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&nologo=true"
        
        os.makedirs("images/blog", exist_ok=True)
        local_image_path = f"images/blog/post_{new_id}.jpg"
        try:
            print(f"Downloading AI image...")
            img_res = requests.get(pollinations_url, timeout=60)
            img_res.raise_for_status()
            with open(local_image_path, 'wb') as f:
                f.write(img_res.content)
            image_url = local_image_path
        except Exception as e:
            print(f"Error downloading image: {e}")
            image_url = "assets/logo.png"
        
        post_entry = {
            "id": new_id,
            "date": today_str,
            "category": new_post.get("category", "Industry News"),
            "title": new_post.get("title", story['original_title']),
            "summary": new_post.get("summary", ""),
            "content": content,
            "original_title": story['original_title'],
            "image": image_url
        }
        
        blog_data.insert(0, post_entry)
        prune_images(blog_data)
        save_blog(blog_data)
        print(f"SUCCESS: Added new article '{post_entry['title']}' to blog.json")
    else:
        sys.exit("CRITICAL ERROR: Failed to rewrite story. Sentinel sounding the alarm.")

if __name__ == "__main__":
    run_sentinel()
