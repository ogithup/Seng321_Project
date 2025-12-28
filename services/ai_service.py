import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve API Key from environment variables
API_KEY = os.getenv('GEMINI_API_KEY')

if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("ERROR: GEMINI_API_KEY not found! Please check your .env file.")

class AIService:
    @staticmethod
    def evaluate_writing(text_content):
        """
        Analyzes student writing using the Gemini AI model.
        Returns a JSON object containing score, errors, and feedback.
        """
        # Using gemini-1.5-flash for fast and efficient processing
        model = genai.GenerativeModel('gemini-1.5-flash') 
        
        prompt = f"""
        You are an experienced English teacher. Analyze the following student writing submission:
        
        "{text_content}"
        
        Please provide the output strictly in valid JSON format with the following keys:
        - score: An integer between 0 and 100 representing the quality.
        - grammar_errors: A list of strings, each describing a specific grammar mistake found.
        - vocabulary_suggestions: A list of strings suggesting better vocabulary usage.
        - general_feedback: A supportive short paragraph summarizing the student's performance.
        
        Do not use markdown formatting (like ```json). Just return the raw JSON object.
        """
        
        try:
            response = model.generate_content(prompt)
            # Clean potential markdown formatting from the response
            clean_text = response.text.strip().replace('```json', '').replace('```', '')
            result = json.loads(clean_text)
            return result
            
        except Exception as e:
            print(f"AI Service Execution Error: {e}")
            return {
                "score": 0,
                "grammar_errors": [f"AI error: {str(e)}"],
                "vocabulary_suggestions": [],
                "general_feedback": "Could not process AI request."
            }