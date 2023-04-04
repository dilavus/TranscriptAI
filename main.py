
import os
import shutil
import subprocess
import sys
import optparse
import time
import datetime
import filetype as filetype
import openai

from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from pydub import AudioSegment
from pydub.silence import detect_silence
from typing import Any
from functools import wraps


class InputFile(object):

    def __init__(self, INPUT_FILE, script_path, supported_files):
        self.FILE_TYPE = None
        self.file = INPUT_FILE
        self.filename = self.getFilename(INPUT_FILE, script_path, supported_files)
        self.filetype = self.fileType(INPUT_FILE, supported_files)
        if self.filetype == 'mov':
            self.filetype = 'mp4'
        self.filename_full = self.filename + "." + self.filetype
        self.sound = AudioSegment.from_file(self.filename + "." + self.filetype, format=self.filetype)
        self.sound_size = os.path.getsize(self.file)

    def getFilename(self, INPUT_FILE, script_path, supported_files):
        FILENAME = ''
        INPUT_FILE = str(INPUT_FILE)
        has_extension = False
        for file_type in supported_files:
            extension = str("." + file_type)
            if extension in INPUT_FILE:
                FILENAME = INPUT_FILE.replace(extension, "")
                has_extension = True
                break
        if not has_extension:
            FILENAME = INPUT_FILE
        FILENAME = FILENAME.replace(script_path + "\\", "")
        self.filename = FILENAME
        return self.filename

    def fileType(self, INPUT_FILE, supported_files):
        """
        Determines file type of the input file, if it can't find it
        by using file type module, if that fails it will attempt to use the file's
        extension, if it has one
        """
        kind = filetype.guess(INPUT_FILE)
        if kind is None:
            for file_type in supported_files:
                if file_type in INPUT_FILE:
                    self.FILE_TYPE = file_type
                    break
        elif kind.extension in supported_files:
            self.FILE_TYPE = kind.extension
        else:
            self.FILE_TYPE = 'Unsupported'
        return self.FILE_TYPE


def runTime(start_time):
    """Returns a formatted string of total duration time"""
    run_time_string = ""
    total_duration = time.time() - start_time
    total_duration_seconds = int(total_duration // 1)
    total_duration_milliseconds = int((total_duration - total_duration_seconds) * 10000)

    total_hours = int(total_duration_seconds // 3600)
    total_minutes = int(total_duration // 60)

    total_seconds = int(total_duration - (total_minutes * 60))
    total_milliseconds = round(total_duration_milliseconds, 4)

    if total_hours > 0:
        run_time_string = str(total_hours) + " hours, " + str(total_minutes) + " minutes, " + str(
            total_seconds) + " seconds" + str(total_milliseconds) + " milliseconds"
    elif total_hours == 0 and total_minutes > 0:
        run_time_string = str(total_minutes) + " minutes, " + str(total_seconds) + " seconds, " + str(
            total_milliseconds) + " milliseconds"
    elif total_hours == 0 and total_minutes == 0:
        run_time_string = str(total_seconds) + " seconds " + str(total_milliseconds) + " milliseconds"
    return run_time_string


class WavFile(object):
    def __init__(self, FILENAME, WAV_FILE, script_path, recommended_section_length, operation_extension):
        self.filetype = 'wav'
        if operation_extension is None:
            self.filename = FILENAME
        else:
            self.filename = FILENAME + operation_extension
        self.filename_full = self.filename + "." + self.filetype
        self.file = script_path + "/" + self.filename_full
        self.sound = AudioSegment.from_wav(self.filename_full)
        self.duration = len(self.sound)
        self.estimated_sections = int(((self.duration + 1) / 1000) // recommended_section_length + 1)
        self.sound_size = os.path.getsize(self.file)


def convertWAV(INPUT_FILE, FILE_TYPE, FILENAME):
    """
    Converts the input file to wav format
    """
    sound = AudioSegment.from_file(INPUT_FILE, FILE_TYPE)
    AUDIO_OUTPUT_FILE = FILENAME + "-CONVERTED.wav"
    sound.export(AUDIO_OUTPUT_FILE, format="wav")
    return AUDIO_OUTPUT_FILE


def cleanUp(script_path, FILENAME, DELETE_CONVERT=False):
    shutil.rmtree(script_path + '/temp', ignore_errors=True)
    if FILENAME != 'None':
        if os.path.isfile(script_path + '/' + FILENAME + "-EXTRACTED.wav") and DELETE_CONVERT:
            os.remove(script_path + '/' + FILENAME + "-EXTRACTED.wav")
        elif os.path.isfile(script_path + '/' + FILENAME + "-CONVERTED.wav") and DELETE_CONVERT:
            os.remove(script_path + '/' + FILENAME + "-CONVERTED.wav")


def extractAudio(FILE_TYPE, FILENAME, script_path):
    """
    Extracts audio from a video file
    """
    AUDIO_OUTPUT_FILE = FILENAME + "-EXTRACTED.wav"
    if os.path.isfile(script_path + '/' + AUDIO_OUTPUT_FILE):
        os.remove(script_path + '/' + AUDIO_OUTPUT_FILE)

    command = str(f'ffmpeg -i {script_path}/{FILENAME}.{FILE_TYPE} -f wav -vn -ar 44100 -ac 2 -ab 192K \
                  {script_path}/{AUDIO_OUTPUT_FILE}')

    subprocess.call(command, shell=True)
    return AUDIO_OUTPUT_FILE


def soundCheck(input_file_size, wav_file_size):
    completed = False
    if wav_file_size > input_file_size:
        completed = True
    return completed


def detectSilence(sound, ESTIMATED_SECTIONS, min_silence_len):
    silences = detect_silence(sound, min_silence_len, silence_thresh=-16, seek_step=1)
    if len(silences) < ESTIMATED_SECTIONS:
        silences.clear()
        return False, silences
    elif len(silences) >= ESTIMATED_SECTIONS:
        return True, silences


def silenceRanges(silence_ranges, silences_found):
    range_list = []
    while len(silence_ranges) != 0:
        silence = str(silence_ranges[0])
        silence_len = int(len(silence))
        silence_bracket1 = int(silence.index("["))
        space = int(silence.index(' '))
        silence_start = int(silence[silence_bracket1 + 1:space - 1])
        silence_end = int(silence[space + 1:silence_len - 1])
        range_list.append(silence_start)
        range_list.append(silence_end)
        del silence_ranges[0]
    return range_list


def audioSplitter(FILENAME, recommended_section_length, new_sound, TEMP_DIR, range_list, total_sections=0,
                  silence_split=False):
    sections = total_sections
    sections_processed = 0
    section_starts = []
    print(" [+]Splitting audio file...")
    while len(range_list) != 0:
        section_number = sections_processed + 1
        dummy_diff = len(str(int(sections))) - len(str(section_number))
        dummy_zeros = dummy_diff * str(0)
        output_name = TEMP_DIR + "/" + FILENAME + "-" + str(dummy_zeros) + str(section_number) + ".wav"
        start = range_list[0]
        stop = range_list[1]
        sound = new_sound[start:stop]
        sound.export(output_name, format="wav")
        section_starts.append(range_list[0])
        del range_list[1]
        del range_list[0]
        sections_processed += 1
    return section_starts


def audioRanges(recommended_section_length, new_sound, silence_split=False):
    duration = len(new_sound)
    range_list = []
    section_length = recommended_section_length * 1000
    start_range = 0
    while duration != 0:
        if duration <= section_length:
            section = duration
        else:
            section = section_length
        stop_range = start_range + section
        range_list.append(start_range)
        range_list.append(stop_range)
        start_range = stop_range
        duration -= section
    return range_list


def getSnippets(TEMP_DIR):
    """
    Makes a list of all audio snippets in the temp directory
    """
    split_wav = []
    for file in os.listdir(TEMP_DIR):
        if file.endswith(".wav"):
            file_string = TEMP_DIR + "\\" + file
            split_wav.append(file_string)
    total_snippets = len(split_wav)
    return split_wav, total_snippets


def createOutput(FILENAME, STRING_LIST, script_path, total_snippets, section_starts):
    OUTPUT_LIST = []
    TIMESTAMP = str(datetime.datetime.strftime(datetime.datetime.today(), '%Y%m%d-%H%M'))
    OUTPUT_FILENAME = FILENAME + "-" + TIMESTAMP + ".txt"
    line_count = 0
    for line in STRING_LIST:
        line_count += 1

        dummy_diff = len(str(int(total_snippets))) - len(str(line_count))
        dummy_zeros = dummy_diff * str(0)
        string_line_count = str(dummy_zeros) + str(line_count) + "-"

        total_time_output = section_starts[0]
        output_minutes = int(total_time_output // 60000)
        if output_minutes >= 1:
            for minute in range(output_minutes):
                total_time_output -= 60000
        output_seconds = int(total_time_output) // 1000
        if output_seconds >= 1:
            for second in range(output_seconds):
                total_time_output -= 1000
        output_milliseconds = total_time_output
        if len(str(output_minutes)) != 2:
            output_minutes = str(0) + str(output_minutes)
        if len(str(output_seconds)) != 2:
            output_seconds = str(0) + str(output_seconds)
        if len(str(output_milliseconds)) != 2:
            output_milliseconds = str(0) + str(output_milliseconds)
        time_string = (str(output_minutes) + ":" + str(output_seconds) + ":" + str(output_milliseconds) + "-")

        new_line = line.replace(string_line_count, time_string)
        OUTPUT_LIST.append(new_line)
        del section_starts[0]

    with open(script_path + "/" + OUTPUT_FILENAME, "a") as f:
        for line in OUTPUT_LIST:
            f.write(line.encode('utf-8').decode('ascii', 'ignore'))
    f.close()


def runOperations(INPUT_FILE, script_path, thread_count, keep_wav, silence_detection, lang, recommended_section_length):
    """
     All the main functions & operations are run from this function.
     """
    start_time = time.time()
    script_path: str | bytes | Any = os.path.abspath(os.path.dirname(sys.argv[0]))
    supported_files = ['mp3', 'wav', 'm4a', 'mp4', 'mkv', 'mpg', 'avi', 'mpeg', 'mov']
    audio_formats = ['mp3', 'm4a']
    video_formats = ['mp4', 'mkv', 'mpg', 'avi', 'mpeg', 'mov']

    if thread_count is None:
        thread_count = 1
    input_file = InputFile(INPUT_FILE, script_path, supported_files)
    TEMP_DIR = script_path + '\\temp'
    TEMP_FILE = TEMP_DIR + '\\' + input_file.filename + '-TEMP.txt'
    check_required = False

    print("[+]Input File: " + input_file.filename_full)
    """
    File Conversion & Extraction Operations
    """
    if input_file.filetype == 'Unsupported':
        print("[!]ERROR: Unsupported File Type!!!")
        exit()
    elif input_file.filetype in video_formats:
        print(" [+]Extracting Audio from Video...")
        new_sound = extractAudio(input_file.filetype, input_file.filename, script_path)
        operation = 'Extraction'
        operation_extension = "-EXTRACTED"
        check_required = True
    elif input_file.filetype in audio_formats:
        print(" [+]Converting to WAV format...")
        new_sound = convertWAV(input_file.file, input_file.filetype, input_file.filename)
        operation = 'Conversion'
        operation_extension = "-CONVERTED"
        check_required = True
    elif input_file.filetype == 'wav':
        print(" [!]No file conversion or extraction needed!")
        keep_wav = True
        new_sound = input_file.sound
        operation_extension = None

    wav_file = WavFile(input_file.filename, new_sound, script_path, recommended_section_length, operation_extension)

    if check_required:
        completed_conversion = False
        while not completed_conversion:
            test = soundCheck(input_file.sound_size, wav_file.sound_size)
            if test:
                print(" [!]" + operation + " Completed")
                completed_conversion = True
            else:
                time.sleep(5)
                print("  [!]" + operation + " Completed but sound tracks have different size!!!")
                completed_conversion = True

    cleanUp(script_path, 'None')
    if not os.path.exists(TEMP_DIR):
        os.mkdir(TEMP_DIR)

    """
    Splitting Operations
    """
    if wav_file.duration / 1000 < recommended_section_length:
        new_sound_file = TEMP_DIR + '/' + wav_file.filename_full
        shutil.copyfile(wav_file.file, new_sound_file)
        silence_detection = False
    else:
        if silence_detection:
            min_silence_len = 500
            print(" [+]Detecting silence sections...")
            while True:
                silence_found, silence_ranges = detectSilence(wav_file.sound, wav_file.estimated_sections,
                                                              min_silence_len)
                if not silence_found:
                    if min_silence_len == 1000:
                        min_silence_len = min_silence_len // 2
                    elif 500 >= min_silence_len > 200:
                        min_silence_len = min_silence_len - 100
                    elif 200 >= min_silence_len > 100:
                        min_silence_len = min_silence_len - 50
                    elif min_silence_len == 100:
                        SILENCE_DETECTED = False
                        break
                if silence_found:
                    SILENCE_DETECTED = True
                    break
            if SILENCE_DETECTED:
                silences_found = int(len(silence_ranges))
                print("  [!]Found " + str(silences_found) + " silence sections")
                range_list = silenceRanges(silence_ranges, silences_found)
                section_starts = audioSplitter(input_file.filename, recommended_section_length, wav_file.sound,
                                               TEMP_DIR, range_list, silences_found)
            else:
                print("  [!]No suitable silence sections found")
                silence_detection = False
    if not silence_detection:
        range_list = audioRanges(recommended_section_length, wav_file.sound)
        section_starts = audioSplitter(input_file.filename, recommended_section_length, wav_file.sound, TEMP_DIR,
                                       range_list, int(len(range_list)))

    split_wav, total_snippets = getSnippets(TEMP_DIR)

    """
    Transcription Operations
    """

    if total_snippets == 1:
        runTranscription(split_wav, thread_count, TEMP_FILE, total_snippets, lang, single_file=True)
    else:
        runTranscription(split_wav, thread_count, TEMP_FILE, total_snippets, lang)

    checkSuccess(total_snippets, STRING_LIST)

    organizeTemp(STRING_LIST)

    print(" [!]Transcription successful")
    createOutput(input_file.filename, STRING_LIST, script_path, total_snippets, section_starts)

    """
    Clean Up Operations
    """
    if keep_wav:
        cleanUp(script_path, 'None')
    elif not keep_wav:
        cleanUp(script_path, input_file.filename, DELETE_CONVERT=True)

    print("-------------------------------")
    print("[!]Completed Transcription")

    run_time = runTime(start_time)
    print('[!]Entire job took: ' + run_time)
    print("-------------------------------")


def transcribeAudio(snippet, line_count, STRING_LIST, total_snippets, pbar, lang='uk', single_file=False):
    """Transcribes the audio input file/snippets and writes to a temp file"""

    if single_file:
        text = transcribe(snippet, lang)
        text_string = text
    elif not single_file:
        dummy_diff = len(str(int(total_snippets))) - len(str(line_count))
        dummy_zeros = dummy_diff * str(0)
        line_count = str(dummy_zeros) + str(line_count)
        text = transcribe(snippet, lang)
        text_string = str(line_count) + "- " + text
        STRING_LIST.append(text_string + '\n')
    pbar.update(1)


def checkSuccess(total_snippets, string_list):
    """
    There is a delay in outputing transcription to file this loop runs until
    all the transcription lines are completed
    """
    print(" [+]Writing transcription to file...")
    while True:
        time.sleep(2)
        if len(string_list) == int(total_snippets):
            break
    return


def organizeTemp(string_list):
    output_list = string_list
    output_list.sort()


def transcribe(snippet, lang):
    try:
        file = open(snippet, "rb")
        transcription = openai.Audio.transcribe("whisper-1", file)
        text_string = transcription.text
        # text_string = snippet
    except Exception:
        text_string = "!!!ERROR processing audio by OpenAI Whisper-1!!!"

    return text_string


def timeit(method):
    @wraps(method)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = method(*args, **kwargs)
        end_time = time.time()
        print(f" [!]{method.__name__} => {(end_time - start_time) * 1000} ms")

        return result

    return wrapper


@timeit
def runTranscription(split_wav, thread_count, TEMP_FILE, total_snippets, lang, single_file=False):
    """
    Main function to run transcription operation
    """
    results = []
    futures_list = []
    pbar_total = total_snippets
    working_list = []
    line_count = 0

    if single_file:
        with tqdm(total=pbar_total, leave=True, desc=" [+]Transcribing audio file") as pbar:
            working_list.append(split_wav[0])
            for snippet in working_list:
                transcribeAudio(snippet, None, STRING_LIST, total_snippets, pbar, lang, single_file=True)
    elif not single_file:
        snippets_to_complete = total_snippets
        snippets_completed = 0
        with tqdm(total=pbar_total, leave=True, desc=" [+]Transcribing audio file snippets") as pbar:

            while snippets_completed != total_snippets:
                if thread_count > snippets_to_complete:
                    thread_count = snippets_to_complete
                for i in range(thread_count):
                    working_list.append(split_wav[i])
                for i in working_list:
                    del split_wav[0]

                with ThreadPoolExecutor(max_workers=thread_count) as executor:
                    for snippet in working_list:
                        line_count += 1
                        futures = executor.submit(transcribeAudio, snippet, line_count, STRING_LIST, total_snippets, pbar, lang)
                        futures_list.append(futures)

                    for future in futures_list:
                        try:
                            result = future.result(timeout=60)
                            results.append(result)
                        except Exception:
                            results.append(None)

                working_list.clear()
                snippets_to_complete -= thread_count
                snippets_completed += thread_count
    return results


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
                                   '\n -a --api <API key by OpenAI> ' +
                                   '\n -i --interval ')

    parser.add_option('-a', '--api',
                      action='store', dest='api', type='string', help='API key by OpenAI')

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
    apikey = options.api

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

    openai.organization = "org-cUglEaGuH6dQ1kt5uQ9Vtghi"
    openai.api_key = apikey
    try:
        openai.Model.list()
    except openai.error.AuthenticationError:
        print(
            f"Incorrect API key provided: {openai.api_key}.'\n'You can find your API key at https://platform.openai.com/account/api-keys.")
        exit()

    runOperations(INPUT_FILE, script_path, thread_count, keep_wav, silence_detection, lang, section_length)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    STRING_LIST = []
    mainAI()
    print('Ok!')
