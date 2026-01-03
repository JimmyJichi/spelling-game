from flask import Flask, render_template, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix
import random
import json
import sqlite3
import datetime
from contextlib import closing

app = Flask(__name__)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1
)

# Database file
DATABASE = 'quiz_data.db'

# Word groups with US spelling and country-specific equivalents
WORD_GROUPS = [
    {
        "name": "Group 1",
        "level": 1,
        "words": [
            {"us": "canceled", "ca": "cancelled", "gb": "cancelled", "au": "cancelled", "nz": "cancelled"},
            {"us": "traveled", "ca": "travelled", "gb": "travelled", "au": "travelled", "nz": "travelled"},
        ]
    },
    {
        "name": "Group 2",
        "level": 1,
        "words": [
            {"us": "defense", "ca": "defence", "gb": "defence", "au": "defence", "nz": "defence"}
        ]
    },
    {
        "name": "Group 3",
        "level": 1,
        "words": [
            {"us": "learned", "ca": "learnt", "gb": "learnt", "au": "learnt", "nz": "learnt"},
            {"us": "dreamed", "ca": "dreamt", "gb": "dreamt", "au": "dreamt", "nz": "dreamt"}
        ]
    },
    {
        "name": "Group 4",
        "level": 1,
        "words": [
            {"us": "catalog", "ca": "catalogue", "gb": "catalogue", "au": "catalogue", "nz": "catalogue"},
            {"us": "dialog", "ca": "dialogue", "gb": "dialogue", "au": "dialogue", "nz": "dialogue"},
        ]
    },
    {
        "name": "Group 5",
        "level": 2,
        "words": [
            {"us": "tire", "ca": "tire", "gb": "tyre", "au": "tyre", "nz": "tyre"}
        ]
    },
    {
        "name": "Group 6",
        "level": 2,
        "words": [
            {"us": "colorize", "ca": "colourize", "gb": "colourise", "au": "colourise", "nz": "colourise"},
        ]
    },
    {
        "name": "Group 7",
        "level": 3,
        "words": [
            {"us": "program", "ca": "program", "gb": "program", "au": "program", "nz": "program", "note": "computer program"}
        ]
    },
    {
        "name": "Group 8",
        "level": 3,
        "words": [
            {"us": "program", "ca": "program", "gb": "programme", "au": "program", "nz": "programme", "note": "concert program"}
        ]
    }
]

# Level descriptions
LEVEL_DESCRIPTIONS = {
    1: "Words spelled the same in every country other than the US",
    2: "Words spelled differently in non-US countries",
    3: "Words spelled differently depending on context"
}


def init_database():
    """Initialize the SQLite database with required tables."""
    with closing(sqlite3.connect(DATABASE)) as conn:
        cursor = conn.cursor()
        
        # Create quiz_attempts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                final_score INTEGER NOT NULL,
                correct_count INTEGER NOT NULL,
                total_count INTEGER NOT NULL
            )
        ''')
        
        # Create quiz_answers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quiz_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,
                word_index INTEGER NOT NULL,
                is_level1 INTEGER NOT NULL,
                country TEXT,
                user_answer TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id)
            )
        ''')
        
        conn.commit()


def get_db_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def get_statistics():
    """Get quiz statistics from the database."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        
        # Total attempts
        cursor.execute('SELECT COUNT(*) as total FROM quiz_attempts')
        total_attempts = cursor.fetchone()['total']
        
        # Average score
        cursor.execute('SELECT AVG(final_score) as avg_score FROM quiz_attempts')
        avg_result = cursor.fetchone()['avg_score']
        average_score = round(avg_result) if avg_result else 0
        
        # Perfect scores count
        cursor.execute('SELECT COUNT(*) as perfect FROM quiz_attempts WHERE final_score = 100')
        perfect_scores = cursor.fetchone()['perfect']
        
        return {
            'total_attempts': total_attempts,
            'average_score': average_score,
            'perfect_scores': perfect_scores
        }


def select_words():
    """Select one word from each group randomly."""
    selected_words = []
    for group_index, group in enumerate(WORD_GROUPS):
        random_index = random.randint(0, len(group["words"]) - 1)
        word = group["words"][random_index].copy()
        word["groupIndex"] = group_index
        word["level"] = group["level"]
        selected_words.append(word)
    return selected_words


def generate_quiz_data():
    """Generate quiz data by selecting words and organizing by level."""
    selected_words = select_words()
    quiz_data = []
    
    for word in selected_words:
        quiz_data.append({
            "us": word["us"],
            "ca": word["ca"],
            "gb": word["gb"],
            "au": word["au"],
            "nz": word["nz"],
            "note": word.get("note", ""),
            "level": word["level"]
        })
    
    return quiz_data


@app.route('/')
def index():
    """Serve the main quiz page."""
    return render_template('index.html')


@app.route('/api/quiz', methods=['GET'])
def get_quiz():
    """Generate and return quiz data."""
    quiz_data = generate_quiz_data()
    return jsonify({
        "quizData": quiz_data,
        "levelDescriptions": LEVEL_DESCRIPTIONS
    })


@app.route('/api/check', methods=['POST'])
def check_answers():
    """Check user answers against correct answers and save to database."""
    data = request.json
    quiz_data = data.get("quizData", [])
    answers = data.get("answers", [])
    
    # Get client IP address
    ip_address = request.remote_addr
    if request.headers.get('X-Forwarded-For'):
        ip_address = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    
    results = []
    correct_count = 0
    total_count = 0
    
    for i, answer_data in enumerate(answers):
        word_index = answer_data["wordIndex"]
        is_level1 = answer_data.get("isLevel1", False)
        user_answer = answer_data.get("answer", "").strip().lower()
        
        word = quiz_data[word_index]
        result = {
            "wordIndex": word_index,
            "isLevel1": is_level1,
            "correct": False,
            "correctAnswer": None,
            "userAnswer": answer_data.get("answer", "").strip()
        }
        
        if is_level1:
            # For Level 1, check against all 4 countries (they should all be the same)
            correct_answer = word["ca"]  # All countries have the same spelling
            result["correctAnswer"] = correct_answer
            
            total_count += 1
            if user_answer == correct_answer.lower():
                result["correct"] = True
                correct_count += 1
        else:
            # For other levels, check each country separately
            country = answer_data.get("country")
            if country and country in word:
                correct_answer = word[country]
                result["correctAnswer"] = correct_answer
                result["country"] = country
                
                total_count += 1
                if user_answer == correct_answer.lower():
                    result["correct"] = True
                    correct_count += 1
        
        results.append(result)
    
    percentage = round((correct_count / total_count * 100)) if total_count > 0 else 0
    
    # Save to database
    timestamp = datetime.datetime.now().isoformat()
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        
        # Insert quiz attempt
        cursor.execute('''
            INSERT INTO quiz_attempts (ip_address, timestamp, final_score, correct_count, total_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (ip_address, timestamp, percentage, correct_count, total_count))
        
        attempt_id = cursor.lastrowid
        
        # Insert individual answers
        for result in results:
            cursor.execute('''
                INSERT INTO quiz_answers 
                (attempt_id, word_index, is_level1, country, user_answer, correct_answer, is_correct)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                attempt_id,
                result["wordIndex"],
                1 if result["isLevel1"] else 0,
                result.get("country"),
                result["userAnswer"],
                result["correctAnswer"],
                1 if result["correct"] else 0
            ))
        
        conn.commit()
    
    # Get statistics
    stats = get_statistics()
    
    return jsonify({
        "results": results,
        "score": {
            "correct": correct_count,
            "total": total_count,
            "percentage": percentage
        },
        "statistics": stats
    })


if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)

