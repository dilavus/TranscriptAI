import openai

def mainOperation():

    file = open("/path/to/file/openai.mp3", "rb")
    transcription = openai.Audio.transcribe("whisper-1", file)

    print(transcription)

    print("Running Main Console")


def print_hi(string):
    print(string)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':


    # mainOperation()
    print_hi('Hi there!')
