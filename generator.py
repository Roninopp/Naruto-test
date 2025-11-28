# Save this as generator.py and run it
import requests
import json

def download_all_characters():
    all_chars = []
    page = 1
    print("⏳ Downloading characters from API... (This takes 30s)")

    while True:
        # Fetch 50 characters at a time
        url = f"https://narutodb.xyz/api/character?page={page}&limit=50"
        try:
            response = requests.get(url)
            data = response.json()
            
            if not data['characters']:
                break
                
            for char in data['characters']:
                if char.get('images'):
                    entry = {
                        "id": char['id'],
                        "name": char['name'],
                        "image": char['images'][0], 
                        "rarity": "Common" 
                    }
                    all_chars.append(entry)
            
            print(f"✅ Page {page} done. Total: {len(all_chars)}")
            page += 1
            
        except Exception as e:
            break

    # Save the file
    with open("naruto_characters.json", "w") as f:
        json.dump(all_chars, f, indent=4)
    
    print(f"🎉 Success! Created naruto_characters.json with {len(all_chars)} characters.")

if __name__ == "__main__":
    download_all_characters()
