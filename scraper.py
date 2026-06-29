import requests
import json
import random
import sys
import os

SUBREDDITS = ['AskReddit', 'AmItheAsshole', 'nosleep', 'relationship_advice', 'confession']
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

def fetch_viral_story(subreddit='AskReddit', time_filter='week', min_upvotes=1000):
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t={time_filter}&limit=25"
    print(f"Fetching stories from r/{subreddit} (Filter: {time_filter})...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch data from Reddit API: Status {response.status_code}")
            return None
        
        data = response.json()
        posts = data.get('data', {}).get('children', [])
        
        valid_posts = []
        for p in posts:
            post_data = p.get('data', {})
            upvotes = post_data.get('ups', 0)
            num_comments = post_data.get('num_comments', 0)
            title = post_data.get('title', '')
            selftext = post_data.get('selftext', '')
            
            # Skip pinned, meta, or posts without enough upvotes
            if post_data.get('stickied') or upvotes < min_upvotes:
                continue
                
            valid_posts.append({
                'id': post_data.get('id'),
                'subreddit': f"r/{subreddit}",
                'title': title,
                'author': f"u/{post_data.get('author', 'Anonymous')}",
                'body': selftext,
                'upvotes': f"{round(upvotes/1000, 1)}k" if upvotes >= 1000 else str(upvotes),
                'comments_count': f"{round(num_comments/1000, 1)}k" if num_comments >= 1000 else str(num_comments),
                'url': f"https://reddit.com{post_data.get('permalink')}"
            })
            
        if not valid_posts:
            print("No valid posts found matching criteria.")
            return None
            
        # Pick the top or a random viral post
        selected_post = valid_posts[0]
        print(f"Selected Story: '{selected_post['title']}' by {selected_post['author']} ({selected_post['upvotes']} upvotes)")
        
        # Also fetch top 2 comments for the post
        comments_url = f"https://www.reddit.com/r/{subreddit}/comments/{selected_post['id']}.json?limit=5&sort=top"
        comm_resp = requests.get(comments_url, headers=HEADERS, timeout=10)
        selected_post['comments'] = []
        
        if comm_resp.status_code == 200:
            comm_data = comm_resp.json()
            if len(comm_data) > 1:
                comments_list = comm_data[1].get('data', {}).get('children', [])
                count = 0
                for c in comments_list:
                    c_data = c.get('data', {})
                    c_body = c_data.get('body', '')
                    c_author = c_data.get('author', '')
                    c_ups = c_data.get('ups', 0)
                    
                    if c_body and c_author and c_author != 'AutoModerator' and len(c_body) > 10:
                        selected_post['comments'].append({
                            'id': count + 1,
                            'username': f"u/{c_author}",
                            'time': '3h ago',
                            'body': c_body[:300], # Keep comment manageable
                            'upvotes': f"{round(c_ups/1000, 1)}k" if c_ups >= 1000 else str(c_ups)
                        })
                        count += 1
                        if count >= 2:
                            break
                            
        return selected_post
        
    except Exception as e:
        print(f"Error fetching Reddit stories: {e}")
        return None

if __name__ == '__main__':
    sub = sys.argv[1] if len(sys.argv) > 1 else 'AskReddit'
    story = fetch_viral_story(subreddit=sub)
    
    if story:
        output_file = os.path.join(os.path.dirname(__file__), 'story_data.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(story, f, ensure_ascii=False, indent=2)
        print(f"Successfully saved story payload to {output_file}")
