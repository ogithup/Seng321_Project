# 🎓 AI-Driven Student Learning Dashboard

[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1.2-white?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-Latest-003B57?style=for-the-badge&logo=sqlite)](https://www.sqlite.org/)
[![Gemini AI](https://img.shields.io/badge/AI-Gemini_1.5_Flash-orange?style=for-the-badge&logo=google-gemini)](https://aistudio.google.com/)

An intelligent, full-stack English learning ecosystem designed to enhance student writing and speaking skills through **Artificial Intelligence** and **OCR Technology**.

---

## ✨ Key Features

### 🤖 Smart Evaluation
* **AI Writing Analysis:** Leverages **Gemini 1.5 Flash** to provide instant feedback on grammar, vocabulary, and overall quality.
* **OCR Integration:** Uses **Tesseract OCR** to digitize and grade handwritten assignments from image uploads.

### 📊 Comprehensive Dashboards
* **Student Hub:** View real-time performance charts, track grade history, and manage personal learning goals.
* [cite_start]**Instructor Portal:** Centralized management to monitor class progress, review all student submissions, and manually adjust grades. [cite: 1]

---

## 🛠️ Tech Stack

| Component | Technology |
| :--- | :--- |
| **Backend** | Python / Flask |
| **Database** | SQLite / SQLAlchemy |
| **AI/ML** | Google Gemini API |
| **OCR** | Pytesseract & Pillow |
| **Frontend** | HTML5, CSS3, Jinja2 |

---

## 🚀 Getting Started

### 1. Requirements
* Python 3.10+
* **Tesseract OCR** installed on your local machine.

### 2. Installation & Setup
Copy and paste the following commands into your terminal:

# Clone the repository
git clone <your-repository-url>

# Enter the directory
cd Seng321_Project

# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install all dependencies
python -m pip install -r requirements.txt

# Create your .env file and add your keys
# SECRET_KEY=your_secret_key
# GEMINI_API_KEY=your_google_api_key
# TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe