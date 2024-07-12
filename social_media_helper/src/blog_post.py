import os
from urllib.parse import urlparse, parse_qs

import click
from dotenv import dotenv_values
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi

# Load environment variables from .env file
config = dotenv_values(os.path.join(".env"))

OPENAI_API_KEY = config.get('OPENAI_API_KEY')
OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)


def extract_video_id(url):
    """Extracts video ID from the full YouTube URL."""
    if "youtube.com" in url:
        parsed_url = urlparse(url)
        video_id = parse_qs(parsed_url.query).get('v')
        if video_id:
            return video_id[0]
    elif "youtu.be" in url:
        return url.split('/')[-1]
    return url  # Assumes that the input is already the ID if no URL pattern matches.


def get_youtube_transcript(video_id, lang='en'):
    """Retrieve the transcript for a given YouTube video ID."""
    try:
        transcript_items = YouTubeTranscriptApi.get_transcript(video_id, languages=(lang,))
        transcript_text = ' '.join([item['text'] for item in transcript_items])
        return transcript_text
    except Exception as e:
        print(f"Error retrieving transcript: {e}")
        return ''


def generate_blog_post(transcript):
    """Use OpenAI's GPT-4 model to generate a blog post from the provided transcript."""
    try:
        chat_completion = OPENAI_CLIENT.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": "You help to create very short, well-structured and engaging blog posts from the long texts provided to you. "
                               "You don't use any markup in your results",
                },
                {
                    "role": "user",
                    "content": f"Create a concise, well-structured, engaging post up to 120 words in English language based on the following video transcript:\n{transcript}"
                }
            ],
            model="gpt-4-turbo",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Error using OpenAI API: {e}")
        return None


@click.command()
@click.option('--video-url', prompt='YouTube Video URL', help='Enter the full YouTube video URL or the video ID.')
@click.option('--lang', default='en', help='Language for the transcript.')
def main(video_url, lang):
    print(f"Retrieving transcript for video {video_url} in {lang}")
    video_id = extract_video_id(video_url)
    print(f"YouTube Video ID: {video_id}")
    transcript = get_youtube_transcript(video_id, lang)
    print(f"Transcript length: {len(transcript)} characters")
    if not transcript:
        print("Failed to retrieve transcript.")
        return

    blog_post = generate_blog_post(transcript)
    if not blog_post:
        print("Failed to generate blog post.")
        return
    print("Generated Blog Post:")
    print(f"Blog Post length: {len(blog_post)} characters")
    print("-" * 100)
    print(blog_post)
    print("-" * 100)


if __name__ == "__main__":
    main()
