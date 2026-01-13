import os
from resend import Resend

# Initialize Resend client
client = Resend(api_key=os.environ.get("RESEND_API_KEY"))

def send_onboarding_email(to_email: str, user_name: str):
    """
    Send onboarding email to the user
    
    Args:
        to_email: Recipient email address
        user_name: Name of the user
    """
    try:
        email = client.emails.send(
            {
                "from": "onboarding@resend.dev",
                "to": to_email,
                "subject": "Welcome to Our Service",
                "html": f"""
                <html>
                    <body>
                        <h1>Welcome {user_name}!</h1>
                        <p>Thank you for signing up. We're excited to have you on board.</p>
                        <p>If you have any questions, feel free to reach out to us.</p>
                        <br>
                        <p>Best regards,<br>The Team</p>
                    </body>
                </html>
                """
            }
        )
        print(f"Email sent successfully to {to_email}")
        return email
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        raise

def send_notification_email(to_email: str, subject: str, message: str):
    """
    Send notification email to the user
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        message: Email message content
    """
    try:
        email = client.emails.send(
            {
                "from": "onboarding@resend.dev",
                "to": to_email,
                "subject": subject,
                "html": f"""
                <html>
                    <body>
                        <h2>{subject}</h2>
                        <p>{message}</p>
                        <br>
                        <p>Best regards,<br>The Team</p>
                    </body>
                </html>
                """
            }
        )
        print(f"Notification email sent to {to_email}")
        return email
    except Exception as e:
        print(f"Error sending notification email: {str(e)}")
        raise

if __name__ == "__main__":
    # Example usage
    test_email = "user@example.com"
    test_user = "John Doe"
    
    # Send onboarding email
    send_onboarding_email(test_email, test_user)
    
    # Send notification email
    send_notification_email(
        test_email,
        "Important Update",
        "This is an important notification for you."
    )
