import os
import logging
import asyncio
from typing import Optional
import resend

# Initialize Resend with API key
resend.api_key = os.getenv("RESEND_API_KEY")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

RECIPIENT_EMAIL = "hihedo1099@proton.me"

def send_log_via_email(subject: str, message: str, log_content: Optional[str] = None) -> bool:
    """
    Send log information via email using Resend API.
    
    Args:
        subject: Email subject
        message: Main message body
        log_content: Optional log content to include
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        email_body = message
        if log_content:
            email_body += f"\n\n--- Log Content ---\n{log_content}"
        
        response = resend.Emails.send({
            "from": "onboarding@resend.dev",
            "to": RECIPIENT_EMAIL,
            "subject": subject,
            "html": f"<p>{email_body.replace(chr(10), '<br>')}</p>"
        })
        
        logger.info(f"Email sent successfully to {RECIPIENT_EMAIL}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email via Resend API: {str(e)}")
        return False

def send_log_via_email_with_attachment(subject: str, message: str, log_file_path: str) -> bool:
    """
    Send log information via email with file attachment using Resend API.
    
    Args:
        subject: Email subject
        message: Main message body
        log_file_path: Path to log file to attach
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        if not os.path.exists(log_file_path):
            logger.error(f"Log file not found: {log_file_path}")
            return False
        
        with open(log_file_path, 'r') as f:
            log_content = f.read()
        
        # For Resend API, we'll include the log content in the email body
        # since attachments require the API to support them
        email_body = message
        if log_content:
            email_body += f"\n\n--- Log File Content ---\n{log_content}"
        
        response = resend.Emails.send({
            "from": "onboarding@resend.dev",
            "to": RECIPIENT_EMAIL,
            "subject": subject,
            "html": f"<p>{email_body.replace(chr(10), '<br>')}</p>"
        })
        
        logger.info(f"Email with log content sent successfully to {RECIPIENT_EMAIL}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email via Resend API: {str(e)}")
        return False

async def main():
    """Main function to demonstrate email sending."""
    logger.info("Starting bot...")
    
    # Example: Send a simple log email
    send_log_via_email(
        subject="Bot Status Report",
        message="Bot is running successfully.",
        log_content="No errors detected."
    )
    
    # Example: Send an error notification
    send_log_via_email(
        subject="Bot Error Alert",
        message="An error occurred during bot execution.",
        log_content="Error traceback information would go here."
    )
    
    logger.info("Bot operations completed.")

if __name__ == "__main__":
    asyncio.run(main())
