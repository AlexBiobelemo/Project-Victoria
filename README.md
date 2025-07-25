# Alex Alagoa Biobelemo
# Project Victoria
Video Demo: https://youtu.be/UtwMr1kedbc?si=0ClIGWv32-Wo-ZXM

Victoria is a full-stack web application engineered to solve a fundamental challenge in self-directed learning: creating a clear, effective, and personalized educational roadmap. The platform empowers users to define a learning goal, and in response, it generates a dynamic, step-by-step curriculum complete with resources and practical challenges. It moves beyond static content by integrating a locally-run Large Language Model (LLM) to provide a context-aware AI Tutor, a neuroscience-based Spaced Repetition System (SRS) for knowledge retention, and a portfolio system to showcase projects.

# Key Features
 * Dynamic Path Generation: A custom algorithm builds a unique, multi-step curriculum tailored to a user's goal.
 * AI-Powered Tutor: A context-aware chatbot, powered by a local Ollama LLM, provides explanations and guidance.
 * Spaced Repetition System (SRS): The application automatically generates flashcards for completed topics to enhance long-term memory.
 * Secure User Authentication: Full user registration and login system with secure password hashing.
 * Role-Based Access: A distinct admin role with privileges to approve or reject user-suggested resources.
 * Interactive Dashboard: A central hub to track progress, manage steps, write personal notes, and rate topics.
 * Comprehensive Security: Hardened against Cross-Site Scripting (XSS) and Cross-Site Request Forgery (CSRF).
 * Light & Dark Mode: A seamless, persistent light/dark theme toggle for user comfort.

# Architecture & Design Decisions
 * Local LLM vs. Cloud APIs: A core strategic decision was to use a locally-run LLM via Ollama to ensure zero operational costs, 100% user data privacy, and offline functionality.
 * SQLAlchemy ORM vs. Raw SQL: The SQLAlchemy ORM provides robust protection against SQL injection, allows for managing the database schema through clean Python classes, and makes the application portable from SQLite to PostgreSQL.
 * Server-Side Security: Security was treated as a foundational requirement. All forms are protected with Flask-WTF CSRF tokens, and all rendered user content is sanitized with Bleach to prevent XSS attacks.
T
echnical Stack
 * Backend: Python, Flask, SQLAlchemy (ORM)
 * Frontend: HTML5, CSS3, JavaScript, Bootstrap 5, Google Fonts
 * Database: SQLite (Development), designed for PostgreSQL (Production)
 * AI: Ollama (running Google's Gemma model locally)
 * Security: Flask-WTF (CSRF), Bleach (XSS Sanitization)
Local Setup & Usage

To run this project locally, please follow these steps:
1. Prerequisites
 * Python 3.9+
 * Ollama
2. Clone & Setup Environment
# Clone the repository
git clone https://github.com/AlexBiobelemo/Project-Victoria
cd Victoria

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

3. Install Dependencies & Configure
# Install all required Python packages
pip install -r requirements.txt

# Create a .env file for configuration
touch .env

Now, open the newly created .env file and add the following configuration:
SECRET_KEY='your-own-super-secret-and-random-key'
DATABASE_URL='sqlite:///site.db'
OLLAMA_API_URL='http://localhost:11434/api/generate'
OLLAMA_MODEL='gemma:latest'

4. Setup Ollama & Database
Make sure the Ollama application is running in the background.
# Pull the Gemma model for the AI Tutor
ollama pull gemma

# Initialize the database schema
flask init-db

# Populate the database with initial topics and resources
flask import-csv

5. Run the Application
# Run the Flask development server
flask run

Navigate to http://12.0.0.1:5000 in your web browser.

License
This project is licensed under the MIT License. See the LICENSE file for details.


# Contributing
Contributions are welcome! If you have ideas for new features, feel free to open an issue to discuss what you would like to change. The easiest way to contribute is by expanding the curriculum. You can do this by adding new topics, resources, or problems to the .csv data files and submitting a pull request.

# Acknowledgements
 * Inspiration: A special thank you to Harvard University > CS50x > Professor David J. Malan for providing a world-class education that inspired this project's creation. I am truly grateful and God bless you even more.

 * AI Assistants:
   * Grok was utilized for sentiment research and for sourcing the initial data for the .csv files.
   * Google Gemini served as an invaluable AI assistant throughout the development process for debugging complex code and refining the application's architecture and security.
