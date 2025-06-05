# Vision Simulator & Eye Test Game

A Flask web application to demonstrate principles of vision, corrective lenses, and an interactive eye test game.

## Project Structure

(Structure remains the same)

## Setup

1.  **Clone/Download:** Get the project files.
2.  **Virtual Environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Create `uploads` directory:**
    ```bash
    mkdir uploads
    ```
5.  **Add a default image:** Place an image named `default_object.png` into the `static/images/` directory.
6.  **Run the Application:**
    ```bash
    flask run
    ```
    Or, for development mode with auto-reload:
    ```bash
    export FLASK_APP=app.py  # On Windows: set FLASK_APP=app.py
    export FLASK_ENV=development # On Windows: set FLASK_ENV=development
    flask run
    ```
    The application will typically be available at `http://127.0.0.1:5000/`.

## Notes
* Ensure the `uploads` directory is writable by the Flask application.
* The application uses Flask's session management. A `SECRET_KEY` is set in `app.py` for development. For production, ensure this is a strong, unique secret.