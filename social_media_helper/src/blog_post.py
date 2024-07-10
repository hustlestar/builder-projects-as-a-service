import os

from dotenv import dotenv_values
from youtube_transcript_api import YouTubeTranscriptApi

# Load environment variables from .env file
config = dotenv_values(os.path.join(".env"))
OPENAI_API_KEY = config.get('OPENAI_API_KEY')
from openai import OpenAI

client = OpenAI(
    # This is the default and can be omitted
    api_key=OPENAI_API_KEY,
)


def get_youtube_transcript(video_id, lang=('en',)):
    """ Retrieve the transcript for a given YouTube video ID. """
    try:
        # noinspection PyPackageRequirements
        transcript_items = YouTubeTranscriptApi.get_transcript(video_id, languages=lang)
        # Concatenate all transcript parts into a single string
        transcript_text = ' '.join([item['text'] for item in transcript_items])
        return transcript_text
    except Exception as e:
        print(f"Error retrieving transcript: {e}")
        return None


def generate_blog_post(transcript):
    """ Use OpenAI's GPT-4 model to generate a blog post from the provided transcript. """
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": "You help to create very short, well-structured and engaging blog posts from the long texts provided to you. "
                               "You don't use any markup in your results",
                },
                {
                    "role": "user",
                    "content": f"Create a concise, well-structured, engaging and informative post up to 200 words in English language based on the following video transcript:"
                               f"\n{transcript}"
                }
            ],
            model="gpt-4-turbo",
        )
        print('a')
        print(chat_completion)
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Error using OpenAI API: {e}")
        return None


def main(video_id, lang=('en',)):
    # Retrieve the video transcript
    transcript = get_youtube_transcript(video_id, lang=lang)
    if not transcript:
        print("Failed to retrieve transcript.")
        return

    # Generate a blog post based on the transcript
    blog_post = generate_blog_post(transcript)
    if not blog_post:
        print("Failed to generate blog post.")
        return
    else:
        print("Generated Blog Post:")
        print(blog_post)


if __name__ == "__main__":
    main('kQ2PUkNngk0', lang=('ru',))
