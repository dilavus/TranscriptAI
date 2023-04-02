import os
import sys
import optparse
import openai
from pydub import AudioSegment


def printTitle():
    version = '5.0'
    splash = '-----------------------------------\n'
    print(f'{splash}    Audio Transcriber - v {version}\n{splash}')


def mainAI():
    printTitle()

    parser = optparse.OptionParser('Options: ' +
                                   '\n -h --help <show this help message and exit>' +
                                   '\n -f --file <target file> (REQUIRED)' +
                                   '\n -t --threads <threads to use> (10 Default)' +
                                   '\n -k --keep <keep converted/extracted wav file>' +
                                   '\n -l --lang <languages to be converted (uk, ru, e.t...)' +
                                   '\n Splitting Options:' +
                                   '\n -s --silence <silence splitting>' +
                                   '\n -i --interval ')

    parser.add_option('-f', '--file',
                      action='store', dest='filename', type='string', help='specify target file', metavar="FILE")

    parser.add_option('-t', '--threads',
                      action='store', dest='threads', type='int', help='specify amount of threads to use')

    parser.add_option('-k', '--keep',
                      action='store_true', dest='keep', default=False, help='Keep wav file, if converting')

    parser.add_option('-s', '--silence',
                      action='store_true', dest='silence', default=False, help='Will use silence detection & splitting')

    parser.add_option('-l', '--lang', action='store', dest='lang', type="string",
                      help='Specify language for translate')

    parser.add_option('-i', '--interval', action='store', dest='section_interval',
                      type="string", help='Interval in sec of the portion sound file to read')

    (options, args) = parser.parse_args()

    if not options.filename:
        for line in parser.option_list:
            print(line)
        exit()

    script_path = os.path.abspath(os.path.dirname(sys.argv[0]))

    INPUT_FILE = options.filename
    thread_count = options.threads
    keep_wav = options.keep
    silence_detection = options.silence
    lang = options.lang
    section_length = int(options.section_interval)

    if lang is None:
        print("[!]Default language is English!\n")
        lang = 'en'

    if INPUT_FILE is None:
        print("[!]No Input File Supplied!\n")
        print(parser.usage)
        exit()
    else:
        while True:
            if os.path.isfile("/" + str(INPUT_FILE)):
                INPUT_FILE = str(INPUT_FILE)
                break
            elif os.path.isfile(script_path + "\\" + str(INPUT_FILE)):
                INPUT_FILE = str(script_path + "\\" + INPUT_FILE)
                break
            else:
                print("[!]ERROR: Cannot find specified file!")
                exit()

    # runOperations(INPUT_FILE, script_path, thread_count, keep_wav, silence_detection, lang, section_length)


def testOperation():
    openai.organization = "org-cUglEaGuH6dQ1kt5uQ9Vtghi"
    openai.api_key = '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'
    openai.Model.list()

    file = open("Guittard-02.mp3", "rb")

    song = AudioSegment.from_mp3("Guittard-02.mp3")
    # PyDub handles time in milliseconds
    ten_minutes = 1 * 60 * 1000
    first_10_minutes = song[:ten_minutes]
    first_10_minutes.export("Guittard-02_10.mp3", format="mp3")
    transcription = openai.Audio.transcribe("whisper-1", file, verbose=True)
    print(transcription.text)


def print_hi(string):
    print(string)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    mainAI()
    # mainOperation()
    print_hi('Hi there!')
