from flask import Flask, request, jsonify, render_template
import openai
from dotenv import load_dotenv
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re
import requests

def get_weather(lat, lon):
    API_KEY = os.getenv('WEATHER_API_KEY')
    base_url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&units=imperial&appid={API_KEY}"
    response = requests.get(base_url)
    data = response.json()

    if response.status_code == 200:
        current_weather = data["current"]
        temperature = current_weather["temp"]
        weather_description = current_weather["weather"][0]["description"]
        wind_speed = current_weather["wind_speed"]  # Extracting wind speed

        # Checking if it's windy based on the wind speed
        windy_status = "It's windy" if wind_speed > 10 else "It's not windy"

        return f"The current temperature is {temperature}°F with {weather_description}. {windy_status}."
    else:
        return f"Sorry, I couldn't find the weather for the provided coordinates."

def get_lat_lon_google(city_name):
    API_KEY = os.getenv('GOOGLE_API_KEY')
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": city_name,
        "key": API_KEY
    }
    response = requests.get(base_url, params=params)
    data = response.json()
    
    # Print the entire response to inspect for errors
    print(data)

    if data['status'] == 'OK':
        latitude = data['results'][0]['geometry']['location']['lat']
        longitude = data['results'][0]['geometry']['location']['lng']
        return latitude, longitude
    else:
        print(f"Failed to get latitude and longitude for {city_name}")
        return None, None

openai.api_key = os.getenv("OPENAI_API_KEY")
mail_pass = os.getenv("Password")

application = Flask(__name__)

def send_email(subject, message, from_addr, to_addr, smtp_server, smtp_port, smtp_user, smtp_pass):
    msg = MIMEMultipart()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = subject

    msg.attach(MIMEText(message, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        text = msg.as_string()
        server.sendmail(from_addr, to_addr, text)
        server.quit()
        print("Email successfully sent to ", to_addr)
    except smtplib.SMTPAuthenticationError:
        print("SMTP Authentication Error: Could not log in to the email account.")
    except smtplib.SMTPException as e:
        print("SMTP Error: ", str(e))
    except Exception as e:
        print("Failed to send email due to error: ", str(e))


def validate_email(email):
    email_regex = re.compile(r'[^@]+@[^@]+\.[^@]+')
    return email_regex.match(email)

def get_email_and_courses(chat_messages):
    email = None
    course_list = {
        "ux": "UX/Product Design", 
        "ai": "AI and Reinforcement Learning", 
        "data": "Data Visualization",
        "cstugpt": "CSTUGPT", 
        "python": "Python For AI", 
        "security": "Security (Seminar)"
    }
    enrolled_courses = []
    is_registration_started = False
    
    for message in chat_messages:
        content = message['content'].lower()
        
        # extract email
        if email is None:
            match = re.search(r'[\w\.-]+@[\w\.-]+', content)
            if match:
                email = match.group(0)
        
        # Start registering courses when the assistant is asking for course names
        if 'let me know' in content:
            is_registration_started = True

        # extract enrolled courses
        if is_registration_started and message['role'] == 'user':
            for course in course_list.keys():
                if course in content:
                    enrolled_courses.append(course_list[course])
        
        # Stop registering courses when the assistant finishes registration
        if 'is there anything else' in content:
            is_registration_started = False

    # remove duplicates from the list
    enrolled_courses = list(set(enrolled_courses))

    return email, enrolled_courses


chatContext = [{'role':'system', 'content': f"""
    You name is Maggie, and you are a smart and friendly virtual assistant designed to enhance student engagement. Please start by greeting the student
    and offering assistance with registering for July courses with one sentence.

    If a student wishes to register for a different time period, kindly apologize and explain that registration 
    is currently only open for July. If a student requires other functions besides registration, ask them to
    check other corresponding web pages.

    Begin by greeting the student and then proceed with the registration process for the July course selection. 
    Ask for email, inform them that they will receive a confirmation email upon completion.

    After collecting all registrations, summarize them and check if the student wishes to enroll in any additional courses.

    Please review the following course list and respond in a short, conversational, and friendly manner.
    The course includes:
    - UX/Product Design Instructor: Xinyu, Time Saturday morning 9:30-11:30
    - AI and Reinforcement Learning, Instructor: YC,  Time: Monday night 19:30-21:00 and Saturday 15:10-17:10
    - Data Visualization, Instuctor: George,  Time: Tuesday night 19:30-21:00 and Saturday 13:30 - 15:00
    - CSTUGPT， Instructor: Michael, Time: Wednesday night 19:30-21:30
    - Python For AI,  Insturctor: Glen, Time: Thursday night: 19:30-21:30
    - Security (Seminar), Insturctor: Wickey Wang Time: Friday night 19:30-21:30 

    """}]

@application.route('/', methods=['GET'])
def home():
    return render_template('index.html')

@application.route('/chatbot', methods=['POST'])
def chatbot():
    data = request.get_json()
    message = data.get('message', '')
    selected_courses = []
    if "weather in" in message.lower():
        city_name = message.split("in")[-1].strip()  # Extract city name from user message
        lat, lon = get_lat_lon_google(city_name)
        if lat and lon:
            weather_response = get_weather(lat, lon)  # Call the weather function
            return jsonify({'AI': weather_response})  # Return immediately if weather response found
        else:
            return jsonify({'AI': f"Sorry, I couldn't find the coordinates for {city_name}."})

    try:
        chatContext.append({"role": "user", "content": message})
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-0613",
            messages=chatContext,
            max_tokens=200,
        )
        response_message = response['choices'][0]['message']['content']
        chatContext.append({"role": "assistant", "content": response_message})
        
        if "end of chat" in message.lower():  # Detect the end of the chat
            # Parse email and course from chatContext
            email_address, selected_courses = get_email_and_courses(chatContext)

            if email_address and selected_courses:
                # Compose the list of enrolled courses into a single string
                enrolled_courses_string = ', '.join(selected_courses)
                
                send_email(
                    subject="Course Registration Confirmation",
                    message=f"Thank you for registering to the following courses: {enrolled_courses_string}. We look forward to seeing you soon.",
                    from_addr="cstugpt@gmail.com",
                    to_addr=email_address,
                    smtp_server="smtp.gmail.com",
                    smtp_port=587,
                    smtp_user="cstugpt",
                    smtp_pass=mail_pass
                )
        return jsonify({'AI': response_message})
    except Exception as e:
        print(str(e))  # Print the exception message
        return jsonify({'error': str(e)}), 400
@application.errorhandler(500)
def internal_server_error(e):
    return "An internal error occurred. Please try again later.", 500

if __name__ == "__main__":
    application.run(debug=True, host='0.0.0.0', port=80)
