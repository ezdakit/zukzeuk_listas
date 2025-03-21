import requests
import time
import difflib

def fetch_final_content(url, timeout=5, max_duration=60):
    headers = {
        'Accept': 'text/html'
    }
    previous_content = None
    start_time = time.time()
    max_time = start_time + max_duration
    exit_reason = None

    while time.time() < max_time:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            current_content = response.text

            # Prints para depuración
            print(f"Tiempo actual: {time.time()}")
            if previous_content is not None:
                diff = difflib.ndiff(previous_content.splitlines(), current_content.splitlines())
                diff_text = '\n'.join(diff)
                print("Diferencias entre contenido anterior y actual (limitadas a 100 caracteres):")
                print(diff_text[:100] + '...' if len(diff_text) > 100 else diff_text)
            else:
                print("Contenido anterior: None")

            print(f"Tiempo desde última actualización: {time.time() - start_time}")

            if current_content != previous_content:
                previous_content = current_content
                start_time = time.time()
                print("Contenido actualizado, reiniciando temporizador.")
            elif time.time() - start_time >= timeout:
                exit_reason = "timeout"
                print("Contenido no ha cambiado en el tiempo especificado, saliendo del bucle.")
                break

            time.sleep(1)
        except requests.exceptions.RequestException as e:
            print(f"Error al hacer la solicitud: {e}")
            break

    if exit_reason is None:
        exit_reason = "max_duration"

    print("Contenido final:")
    print(current_content)
    print(f"Razón de salida del bucle: {exit_reason}")

if __name__ == "__main__":
    url = "http://127.0.0.1:43110/18cZ4ehTarf34TCxntYDx9T2NHXiBvsVie/?wrapper_nonce=36c675088d663a7f4bc575928f5924ff5bdc2301b739cfc3c752b6d91dbbe011"
    fetch_final_content(url)
