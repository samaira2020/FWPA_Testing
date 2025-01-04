from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_pymongo import PyMongo
from datetime import datetime
from bson.objectid import ObjectId
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = "supersecretkey"

# MongoDB Configuration
app.config["MONGO_URI"] = "mongodb://localhost:27017/Dataset"
mongo = PyMongo(app)

# Admin Emails
ADMIN_EMAILS = [
    "62300291@modul.ac.at", 
    "62104811@modul.ac.at",
    "62400254@modul.ac.at"
]

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "your_email@example.com"  # Replace with your email
SMTP_PASSWORD = "your_password"          # Replace with your email password

# Helper Function: Send Email
def send_email(recipient, subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USERNAME
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, recipient, msg.as_string())
        server.quit()
    except Exception as e:
        print("Error sending email:", e)

# Homepage: Calendar with Events
@app.route("/")
def homepage():
    if not ("student_email" in session or "staff_email" in session or "admin_email" in session):
        return redirect(url_for("login"))

    try:
        event_type_filter = request.args.get("event_type", None)
        query = {}
        if event_type_filter and event_type_filter.lower() != "all":
            query["type_of_event"] = event_type_filter

        # Get approved events from both Events and RequestedEvents collections
        events = list(mongo.db.Events.find(query))
        approved_requests = list(mongo.db.RequestedEvents.find({
            **query,
            "status": "approved"
        }))
        
        # Combine and format all events
        all_events = events + approved_requests
        formatted_events = []
        
        for event in all_events:
            try:
                # Extract date components
                year = event.get('year')
                month = event.get('month')
                day = event.get('day')
                
                if year and month and day:
                    formatted_event = {
                        '_id': str(event['_id']),
                        'event_name': event.get('event_name', ''),
                        'type_of_event': event.get('type_of_event', ''),
                        'location': event.get('location', ''),
                        'description': event.get('description', ''),
                        'contact_information': event.get('contact_information', ''),
                        'event_date': f"{year}-{month:02d}-{day:02d}"
                    }
                    formatted_events.append(formatted_event)
                elif 'event_date' in event:
                    # Handle date string format
                    date_str = str(event['event_date']).split('T')[0]
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    formatted_event = {
                        '_id': str(event['_id']),
                        'event_name': event.get('event_name', ''),
                        'type_of_event': event.get('type_of_event', ''),
                        'location': event.get('location', ''),
                        'description': event.get('description', ''),
                        'contact_information': event.get('contact_information', ''),
                        'event_date': date_obj.strftime('%Y-%m-%d')
                    }
                    formatted_events.append(formatted_event)
                    
            except Exception as e:
                print(f"Error processing event: {event.get('event_name', 'Unknown')}, Error: {str(e)}")
                continue

        # Sort events by date
        formatted_events.sort(key=lambda x: x.get('event_date', ''))
        
        return render_template("Calendar.html", events=formatted_events)
        
    except Exception as e:
        print(f"Error in homepage route: {str(e)}")
        return "Error loading calendar. Please try again later."

# Login Route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").strip()
        password = request.form.get("password")

        # Check admin login
        if email in ADMIN_EMAILS and password == "admin":
            session["admin_email"] = email
            session["admin_name"] = "Admin"
            return redirect(url_for("admin_dashboard"))

        # Check student login
        student = mongo.db.Students.find_one({"Email": email, "Password": password})
        if student:
            session["student_email"] = student["Email"]
            session["student_name"] = student.get("Name", "Student")
            return redirect(url_for("student_dashboard"))

        # Check staff login
        staff = mongo.db.Staff.find_one({"Email": email, "Password": password})
        if staff:
            session["staff_email"] = staff["Email"]
            session["staff_name"] = staff.get("Name", "Staff Member")
            return redirect(url_for("staff_dashboard"))

        return render_template("Login.html", error="Invalid email or password. Please try again.")
    
    return render_template("Login.html")

# Admin: Event Management Page
@app.route("/admin")
def admin_dashboard():
    if "admin_email" not in session:
        return redirect(url_for("login"))
    
    # Get all events, sorted by date
    events = list(mongo.db.Events.find())
    
    # Format dates for display
    for event in events:
        try:
            # Extract date components from the event
            year = event.get('year')
            month = event.get('month')
            day = event.get('day')
            
            if year and month and day:
                # Create a date string in YYYY-MM-DD format
                date_str = f"{year}-{month:02d}-{day:02d}"
                event['event_date'] = date_str
            elif 'date' in event:
                # Handle existing date field if present
                date_str = str(event['date']).split('T')[0]
                event['event_date'] = date_str
        except Exception as e:
            print(f"Error formatting date for event {event.get('event_name', 'Unknown')}: {e}")
            continue
    
    # Sort events by date
    events.sort(key=lambda x: x.get('event_date', ''), reverse=False)
    
    return render_template("Admin.html", events=events)

@app.route("/admin/requests/<event_id>/<action>", methods=["POST"])
def manage_event_request(event_id, action):
    if "admin_email" not in session:
        return redirect(url_for("login"))

    try:
        event = mongo.db.RequestedEvents.find_one({"_id": ObjectId(event_id)})
        if not event:
            flash("Event not found", "error")
            return redirect(url_for("admin_requests"))

        if action == "approve":
            # Parse the date into components
            try:
                date_str = str(event['event_date']).split('T')[0]
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                date_components = {
                    "year": date_obj.year,
                    "month": date_obj.month,
                    "day": date_obj.day
                }
            except (ValueError, KeyError):
                date_components = {}

            # Add the event to the Events collection
            mongo.db.Events.insert_one({
                "event_name": event["event_name"],
                **date_components,  # Add date components
                "type_of_event": event["type_of_event"],
                "location": event["location"],
                "description": event["description"],
                "contact_information": event["contact_information"]
            })
            # Update the status to approved
            mongo.db.RequestedEvents.update_one(
                {"_id": ObjectId(event_id)}, 
                {"$set": {"status": "approved"}}
            )
            flash("Event approved successfully", "success")
        
        elif action == "decline":
            # Update the status to declined
            mongo.db.RequestedEvents.update_one(
                {"_id": ObjectId(event_id)}, 
                {"$set": {"status": "declined"}}
            )
            flash("Event declined", "info")

        return redirect(url_for("admin_requests"))
    
    except Exception as e:
        print(f"Error managing event request: {str(e)}")
        flash("An error occurred while processing the request", "error")
        return redirect(url_for("admin_requests"))

# Staff Dashboard
@app.route("/staff-dashboard")
def staff_dashboard():
    if "staff_email" not in session:
        return redirect(url_for("login"))

    user_email = session["staff_email"]
    # Get favorite events for the staff member
    favourites = list(mongo.db.Favourites.find({"user_email": user_email}))
    
    # Format dates for each favorite event
    for event in favourites:
        try:
            if 'year' in event and 'month' in event and 'day' in event:
                # Date components are already present
                continue
            elif 'event_date' in event:
                # Parse the date string into components
                date_obj = datetime.strptime(event['event_date'], '%Y-%m-%d')
                event['year'] = date_obj.year
                event['month'] = date_obj.month
                event['day'] = date_obj.day
        except Exception as e:
            print(f"Error formatting date for event: {e}")
            continue
    
    # Get staff information
    staff = mongo.db.Staff.find_one({"Email": user_email})
    
    return render_template("Staff_Dashboard.html", 
                         favourites=favourites,
                         staff=staff)

# Student Dashboard
@app.route("/student-dashboard")
def student_dashboard():
    if "student_email" not in session:
        return redirect(url_for("login"))

    user_email = session["student_email"]
    # Get favorite events for the student
    favourites = list(mongo.db.Favourites.find({"user_email": user_email}))
    
    # Format dates for each favorite event
    for event in favourites:
        try:
            if 'year' in event and 'month' in event and 'day' in event:
                # Date components are already present
                continue
            elif 'event_date' in event:
                # Parse the date string into components
                date_obj = datetime.strptime(event['event_date'], '%Y-%m-%d')
                event['year'] = date_obj.year
                event['month'] = date_obj.month
                event['day'] = date_obj.day
        except Exception as e:
            print(f"Error formatting date for event: {e}")
            continue
    
    # Get student information
    student = mongo.db.Students.find_one({"Email": user_email})
    
    return render_template("Student_Dashboard.html", 
                         favourites=favourites,
                         student=student)

# Event Details
@app.route("/event-details")
def event_details():
    if not ("student_email" in session or "staff_email" in session or "admin_email" in session):
        return redirect(url_for("login"))

    event_id = request.args.get('event_id')
    
    # If event_id is provided, get that specific event
    if event_id:
        try:
            event = mongo.db.Events.find_one({"_id": ObjectId(event_id)})
            if not event:
                # Check in RequestedEvents if not found in Events
                event = mongo.db.RequestedEvents.find_one({
                    "_id": ObjectId(event_id),
                    "status": "approved"
                })
            
            if event:
                # Format the event date
                try:
                    if 'year' in event and 'month' in event and 'day' in event:
                        event['event_date'] = f"{event['year']}-{event['month']:02d}-{event['day']:02d}"
                    elif 'event_date' in event:
                        date_str = str(event['event_date']).split('T')[0]
                        event['event_date'] = date_str
                except Exception as e:
                    print(f"Error formatting date: {e}")
                    event['event_date'] = ''
                
                return render_template("EventDetails.html", events=[event])
        except Exception as e:
            print(f"Error fetching event: {e}")
    
    # If no event_id or event not found, show all events
    events = list(mongo.db.Events.find())
    
    # Format dates for display
    for event in events:
        try:
            if 'year' in event and 'month' in event and 'day' in event:
                event['event_date'] = f"{event['year']}-{event['month']:02d}-{event['day']:02d}"
            elif 'event_date' in event:
                date_str = str(event['event_date']).split('T')[0]
                event['event_date'] = date_str
        except Exception as e:
            print(f"Error formatting date: {e}")
            event['event_date'] = ''
            continue

    # Sort events by date
    events.sort(key=lambda x: x.get('event_date', ''), reverse=False)
    
    return render_template("EventDetails.html", events=events)

# Request Event
@app.route("/request-event", methods=["GET", "POST"])
def request_event():
    if "student_email" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        event_name = request.form["event_name"]
        event_date = request.form["event_date"]
        event_time = request.form["event_time"]
        event_location = request.form["event_location"]
        event_description = request.form["event_description"]
        contact_information = request.form["contact_information"]
        event_type = request.form["event_type"]

        event_datetime = f"{event_date} {event_time}" if event_time else event_date
        mongo.db.RequestedEvents.insert_one({
            "event_name": event_name,
            "event_date": event_datetime,
            "location": event_location,
            "description": event_description,
            "contact_information": contact_information,
            "type_of_event": event_type,
            "status": "pending"
        })
        send_email(ADMIN_EMAIL, "New Event Request", f"A new event '{event_name}' has been requested.")
        return redirect(url_for("feedback"))
    return render_template("RequestEvent.html")

# Feedback Page
@app.route("/feedback")
def feedback():
    return render_template("Feedback.html")

# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Add this new route after your admin_dashboard route
@app.route("/pending-requests")
def pending_requests():
    if "admin_email" not in session:
        return redirect(url_for("login"))
    
    # Get pending requests
    requested_events = list(mongo.db.RequestedEvents.find({"status": "pending"}))
    return render_template("PendingRequests.html", requested_events=requested_events)

# Admin: Delete Event
@app.route("/admin/delete/<event_id>", methods=["POST"])
def delete_event(event_id):
    if "admin_email" not in session:
        return redirect(url_for("login"))
    
    try:
        # Delete the event from the Events collection
        result = mongo.db.Events.delete_one({"_id": ObjectId(event_id)})
        
        if result.deleted_count > 0:
            flash("Event deleted successfully", "success")
        else:
            flash("Event not found", "error")
            
    except Exception as e:
        print(f"Error deleting event: {str(e)}")
        flash("An error occurred while deleting the event", "error")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/requests")
def admin_requests():
    if "admin_email" not in session:
        return redirect(url_for("login"))
    
    requested_events = list(mongo.db.RequestedEvents.find({"status": "pending"}))
    
    # Format dates for display
    for event in requested_events:
        try:
            if 'event_date' in event:
                date_str = str(event['event_date']).split('T')[0]
                event['event_date'] = date_str
        except Exception as e:
            print(f"Error formatting date: {e}")
            event['event_date'] = ''
    
    requested_events.sort(key=lambda x: x.get('event_date', ''), reverse=False)
    
    return render_template("AdminRequests.html", requested_events=requested_events)

@app.route("/get-event/<event_id>")
def get_event(event_id):
    if "admin_email" not in session:
        return redirect(url_for("login"))
    
    event = mongo.db.Events.find_one({"_id": ObjectId(event_id)})
    if event:
        try:
            # Extract date components
            year = event.get('year')
            month = event.get('month')
            day = event.get('day')
            
            if year and month and day:
                # Create a date string in YYYY-MM-DD format
                event['event_date'] = f"{year}-{month:02d}-{day:02d}"
            elif 'date' in event:
                event['event_date'] = str(event['date']).split('T')[0]
        except Exception as e:
            print(f"Error formatting date: {e}")
            event['event_date'] = ''
    
    event['_id'] = str(event['_id'])
    return jsonify(event)

@app.route("/update-event", methods=["POST"])
def update_event():
    if "admin_email" not in session:
        return redirect(url_for("login"))
    
    try:
        event_id = request.form.get("event_id")
        event_date = request.form.get("event_date")
        
        # Parse the date into components
        try:
            date_obj = datetime.strptime(event_date, '%Y-%m-%d')
            update_data = {
                "year": date_obj.year,
                "month": date_obj.month,
                "day": date_obj.day,
                "type_of_event": request.form.get("type_of_event"),
                "location": request.form.get("location"),
                "description": request.form.get("description"),
                "contact_information": request.form.get("contact_information")
            }
        except ValueError:
            flash("Invalid date format", "error")
            return redirect(url_for("admin_dashboard"))

        mongo.db.Events.update_one(
            {"_id": ObjectId(event_id)},
            {"$set": update_data}
        )
        
        flash("Event updated successfully", "success")
    except Exception as e:
        print(f"Error updating event: {str(e)}")
        flash("Error updating event", "error")
    
    return redirect(url_for("admin_dashboard"))

@app.template_filter('get_event_color')
def get_event_color(event_type):
    colors = {
        'Modul Events': '#bf3029',
        'Club Events': '#34a853',
        'External Events': '#fbbc05',
        'MCC Events': '#17a2b8'
    }
    return colors.get(event_type, '#6c757d')

@app.template_filter('format_date')
def format_date(date_str):
    try:
        if not date_str:
            return "Date not specified"
            
        # Handle different date formats
        if isinstance(date_str, str):
            if 'T' in date_str:
                date_str = date_str.split('T')[0]
            
        date_obj = datetime.strptime(str(date_str), '%Y-%m-%d')
        return date_obj.strftime('%B %d, %Y')  # Format as "January 15, 2024"
    except (ValueError, TypeError) as e:
        print(f"Date parsing error: {e} for date: {date_str}")
        return str(date_str)

@app.route("/remove-favorite/<event_id>", methods=["POST"])
def remove_favorite(event_id):
    if not ("student_email" in session or "staff_email" in session):
        return redirect(url_for("login"))
    
    try:
        user_email = session.get("student_email") or session.get("staff_email")
        result = mongo.db.Favourites.delete_one({
            "_id": ObjectId(event_id),
            "user_email": user_email
        })
        
        if result.deleted_count > 0:
            flash("Event removed from favorites", "success")
        else:
            flash("Event not found", "error")
            
    except Exception as e:
        print(f"Error removing favorite: {str(e)}")
        flash("Error removing event from favorites", "error")
    
    return redirect(url_for("staff_dashboard" if "staff_email" in session else "student_dashboard"))

@app.route("/add-favorite", methods=["POST"])
def add_favorite():
    if not ("student_email" in session or "staff_email" in session):
        return redirect(url_for("login"))
    
    try:
        event_name = request.form["event_name"]
        event_date = request.form["event_date"]
        category = request.form["category"]
        location = request.form["location"]
        description = request.form["description"]
        contact_information = request.form["contact_information"]
        user_email = session.get("student_email") or session.get("staff_email")

        # Parse the date into components
        try:
            date_obj = datetime.strptime(event_date, '%Y-%m-%d')
            date_components = {
                "year": date_obj.year,
                "month": date_obj.month,
                "day": date_obj.day
            }
        except ValueError:
            date_components = {}

        mongo.db.Favourites.update_one(
            {"user_email": user_email, "event_name": event_name},
            {"$set": {
                "event_name": event_name,
                **date_components,  # Add date components
                "category": category,
                "location": location,
                "description": description,
                "contact_information": contact_information,
                "user_email": user_email
            }},
            upsert=True
        )
        flash("Event added to favorites", "success")
        return redirect(url_for('event_details'))
    except Exception as e:
        print(f"Error adding favorite: {str(e)}")
        flash("Error adding event to favorites", "error")
        return redirect(url_for('event_details'))

# Run the App
if __name__ == "__main__":
    app.run(debug=True, port=5010)
