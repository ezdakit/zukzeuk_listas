import requests
import time

def fetch_final_content(url, timeout=5):
    headers = {
        'Accept': 'text/html'
    }
    previous_content = None
    start_time = time.time()

    while True:
        response = requests.get(url, headers=headers)
        current_content = response.text

        if current_content != previous_content:
            previous_content = current_content
            start_time = time.time()
        elif time.time() - start_time >= timeout:
            break

        time.sleep(1)

    print(current_content)

if __name__ == "__main__":
    url = "http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie/?wrapper_nonce=36c675088d663a7f4bc575928f5924ff5bdc2301b739cfc3c752b6d91dbbe011"
    fetch_final_content(url)
