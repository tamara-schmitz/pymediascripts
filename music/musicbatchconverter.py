#!/usr/bin/python3

# Requires ffmpeg command!

import os
import shutil
from pathlib import Path
import unicodedata
import textwrap
import argparse
import sys
import subprocess
import tempfile
import random
import string
import re
from concurrent import futures

def exec_cmd(cmd, output=None):
    if isinstance(cmd, str):
        cmd = cmd.split(' ')

    if sys.platform == 'win32':
        # TODO priority does not appear to be set properly
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.BELOW_NORMAL_PRIORITY_CLASS
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT, startupinfo=si)
    elif sys.platform == 'linux' or sys.platform == 'darwin':
        cmd.insert(0, "nice")
        cmd.insert(1, "-n19")
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)
    else:
        if args.v:
            print("  Executing command: {}".format(cmd))
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)

def random_string(length: int) -> str:
    chars = string.ascii_uppercase
    rnd_str = ""
    for num in range(length):
        rnd_str += random.choice(chars)
    return rnd_str

def make_fat32_compatible(file_path: Path) -> Path:
    # Define a regular expression pattern for illegal characters
    illegal_chars_pattern = re.compile(r'[<>:"/\\|?*\u0000-\u001F\u007F-\u009F]')

    # Replace any illegal characters and unsupported Unicode characters with valid ones
    fat32_compatible_path = []

    # Evaluate each blob of the path
    for element in file_path.parts:
        if element == file_path.anchor:
            fat32_compatible_path.append(element)
        else:
            element_str = ""
            for char in element:
                if illegal_chars_pattern.match(char):
                    element_str += '_'
                elif unicodedata.category(char) in ['Mn', 'Me', 'Cf', 'Cc']:
                    # Ignore combining, enclosing, formatting, and control characters
                    pass
                elif ord(char) > 0xFFFF:
                    # Ignore characters beyond the BMP
                    pass
                else:
                    element_str += char

            # Ensure that the resulting path doesn't exceed the maximum length limit of FAT32
            element_str = element_str.strip()[:255]
            fat32_compatible_path.append(element_str)

    return Path(*fat32_compatible_path)

# Argument custom validators
def remove_empty_from_list(li):
    try:
        while True:
            li.remove('')
    except ValueError:
        pass
    return li
def pop_element_from_list(li, el) -> list:
    try:
        li.remove(el)
    except ValueError:
        pass
    return li

def argcheck_ifm(string) -> list:
    if_mask = string.strip().lower().split(',')
    for el in if_mask:
        if el.startswith('.'):
            el = el[1:]
        if not el.isalnum:
            print('Expected a list of file endings like: flac,wav,wave,mp3')
            raise argparse.ArgumentError()
    return list(remove_empty_from_list(if_mask))
def argcheck_ofm(string) -> str:
    of_mask = string.strip().lower()
    if of_mask.startswith('.'):
        of_mask = of_mask[1:]
    if not of_mask.isalnum:
        print('Expected a file ending like: ogg')
        raise argparse.ArgumentError()
    return of_mask
def argcheck_cfm(string) -> str:
    cf_mask = string.strip().lower()
    if cf_mask == "*" or cf_mask == "all":
        cf_mask = "*"
    for el in cf_mask.split(','):
        if el.startswith('.'):
            el = el[1:]
        if not el.isalnum:
            print('Expected either \'*\', \'all\' or \
                   a list of file endings like: \'url,png,jpg,bmp\'')
            raise argparse.ArgumentError()
    return cf_mask
def argcheck_ffpath(string) -> str:
    ffpath = string.strip()
    if 'ffmpeg' not in ffpath:
        print('Expected a valid path or environment to ffmpeg like: ffmpeg')
        raise argparse.ArgumentError()
    return ffpath
def argcheck_ffargs(string) -> list:
    ffargs = string.strip().split(' ')
    if '-c:a' not in ffargs:
        print('Expected a valid audio codec string in \" like: \"-c:a libvorbis -q:a 7')
        raise argparse.ArgumentError()
    return list(remove_empty_from_list(ffargs))

def argcheck_preset(string) -> int:
    string = string.lower()
    if string == "smaller":
        return 1
    elif string == "compatible":
        return 2
    elif string == "dynamic_compressed":
        return 3
    elif string == "normalized":
        return 4
    elif string == "mp4walkman":
        return 6
    elif string == "cd-wav":
        return 10
    elif string == "flac":
        return 11
    elif string == "cd-flac":
        return 12
    elif string == "":
        return 0
    else:
        print('Invalid Preset specified')
        raise argparse.ArgumentError()

# Argument handling
try:
    descrp = textwrap.dedent('''\
            Copys an input directory to a destination and converts applicable files to one desired output format. Say a music folder full of FLACs, MP3, PNGs will be copied but the FLACs are converted to OGG.

    --Example usages--

    Simple:
    ./musicbatchconverter.py music-album /phone/music-album

    To 320kbs MP3 using presets:
    ./musicbatchconverter.py --preset 3 music-album /phone/music-album

    Other filter and conversion to MP3:
    ./musicbatchconverter.py -ifm "flac,wav,aif,aac" -ofm mp3 -ffargs "-c:a libmp3lame -b:a 224k" -vff music-album /phone/music-album

    Using a custom ffmpeg version from a container
    ./musicbatchconverter.py -v -ffpath "podman run --rm -v $PWD:/temp/ zennoe/ffmpeg-docker-ost" /temp/music-album /temp/out
    ''')
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=descrp)

    parser.add_argument("input_dir", type=Path, help="path to input folder. Use \\ or \" for names with spaces")
    parser.add_argument("output_dir", type=Path, help="output folder. Use \\ or \" for names with spaces")
    parser.add_argument("--ignore-dir", type=Path, help="Ignore directory with the specified folder name.")
    parser.add_argument("--ignore-not-empty", action="store_true", help="continue even if the output directory contains files. This overwrites existing files.")
    parser.add_argument("-ifm", "--inputfilemask", dest="ifm", default="flac,wav,aif,aiff,ape,dsd,mp3,ogg,opus,mka,m4a,wma,mp4,aac", type=argcheck_ifm, help="Filter mask defining which files will be converted. Other files are copied")
    parser.add_argument("-ofm", "--outputformat", dest="ofm", default="ogg", type=argcheck_ofm, help="Output format of converted files")
    parser.add_argument("-cfm", "--copyfilemask", dest="cfm", default="*", type=argcheck_cfm, help="Do not copy files that match any entry in this list. * or all means do not copy any not-converted files.")
    parser.add_argument("-ffpath", "--ffmpegpath", dest="ffpath", default="ffmpeg", type=argcheck_ffpath, help="Path to ffmpeg")
    parser.add_argument("-ffargs", "--ffmpegarguments", dest="ffargs", type=argcheck_ffargs, help="Codec options to submit to ffmpeg")
    parser.add_argument("-max_workers", default=os.cpu_count(), type=int, help="Set max parallel converter tasks. By default is your CPU thread count.")
    parser.add_argument("-v", "--verbose", dest="v", help="Verbose mode", action="store_true")
    parser.add_argument("-vff", "--verboseffmpeg", dest="vff", help="Verbose mode for ffmpeg", action="store_true")
    parser.add_argument("-p", "--preset", default="", type=argcheck_preset,
                        help="Set a preset that overwrites other arguments. Possible values: smaller (opus), compatible (mp3), dynamic_compressed (mka), normalized (mka), mp4walkman (mp4), cd-wav (wav), flac, cd-flac")
    parser.add_argument("-fat", "--fat32-compatible", dest="fat", help="Ensure that paths and filenames are compliant with FAT32 filesystems", action="store_true")
    parser.add_argument("--no-extract-coverart", dest="nocover", help="Skip the extraction of cover art from metadata", action="store_true")
    parser.add_argument("--always-extract-coverart", dest="alwayscover", help="Always extract cover art from metadata even if existing cover art was found", action="store_true")
    parser.add_argument("--no-copy", dest="nocopy", help="Skip copying non-music files over. Usually all non-converted files are preserved. But setting this option, skips that step.", action="store_true")

    args = parser.parse_args()

except Exception as e:
    print(e)
    exit(-1)

# Check for runtime dependencies
try:
    subprocess.call([ Path(args.ffpath), "-version" ], stdout=subprocess.PIPE, shell=False)

except (subprocess.SubprocessError, FileNotFoundError):
    print("This uses the `ffmpeg` command. You need to make sure that ffmpeg and its dependent codec libraries are installed.")
    print("If you have tried to use `-ffpath` make sure it points to the executable.")
    exit(-1)

if not args.ignore_not_empty and args.output_dir.exists() and len(os.listdir(args.output_dir)) > 0:
    print("Your output directory is not empty. If you continue using --ignore-not-empty existing files may be overwritten")
    exit(-1)

if not args.ffargs and not args.preset:
    print("You neither selected a preset nor set any ffmpeg arguments. Selecting the compatible preset for you...")
    args.preset = 2

# apply preset
if args.preset == 1:
    # smaller
    args.ofm = argcheck_ofm("ogg")
    args.ffargs = argcheck_ffargs("-hide_banner -c:a libopus -b:a 160k -vbr 2 -frame_duration 60 -ac 2")

if args.preset == 2:
    # compatible
    pop_element_from_list(args.ifm, "mp3")
    args.ofm = argcheck_ofm("mp3")
    if not args.ffargs:
        args.ffargs = argcheck_ffargs("-c:a libmp3lame -q:a 1 -compression_level 0 -ac 2")

if args.preset == 3:
    # dynamic_compressed
    args.ofm = argcheck_ofm("mka")
    args.ffargs = argcheck_ffargs("-hide_banner -map 0:a -ac 2 -c copy" +
                                  " -c:a libopus -b:a 192k -vbr 2 -frame_duration 120 " +
                                  " -metadata REPLAYGAIN_ALBUM_GAIN=0 -metadata REPLAYGAIN_ALBUM_PEAK=0.99" +
                                  " -metadata REPLAYGAIN_TRACK_GAIN=0 -metadata REPLAYGAIN_TRACK_PEAK=0.99" +
                                  " -af aresample=osf=flt:osr=192000:filter_type=kaiser,dynaudnorm=r=-18dB")
if args.preset == 4:
    # normalized
    args.ofm = argcheck_ofm("mka")
    args.ffargs = argcheck_ffargs("-hide_banner -map 0:a -ac 2 -c copy" +
                                  " -c:a libopus -b:a 192k -vbr 2 -frame_duration 120" +
                                  " -metadata REPLAYGAIN_ALBUM_GAIN=0 -metadata REPLAYGAIN_ALBUM_PEAK=0.99" +
                                  " -metadata REPLAYGAIN_TRACK_GAIN=0 -metadata REPLAYGAIN_TRACK_PEAK=0.99" +
                                  " -af aresample=osf=flt:osr=192000:filter_type=kaiser,alimiter=limit=-1.0dB:level=off:attack=2:release=50:level_in=")

if args.preset == 6:
    # mp4walkman
    pop_element_from_list(args.ifm, "m4a")
    args.ofm = argcheck_ofm("m4a")
    if not args.ffargs:
        args.ffargs = argcheck_ffargs(" -c:a libfdk_aac -vbr 5 -profile:a aac_low -ac 2 -af aresample=osr=44100:resampler=swr:filter_type=kaiser")

if args.preset == 10:
    # CD-Wav
    args.ofm = argcheck_ofm("wav")
    if not args.ffargs:
        # for limiting after resampling -0.25dB would suffice. but when limiting pre resample -1dB is just quiet enough
        args.ffargs = argcheck_ffargs("-c:a pcm_s16le -af aresample=osf=flt:osr=44100:resampler=swr:filter_type=kaiser,alimiter=limit=-0.1dB:level=off:attack=2.5:release=15,aresample=osf=s16:dither_method=triangular_hp")

if args.preset == 11:
    # Flac
    pop_element_from_list(args.ifm, "flac")
    args.ofm = argcheck_ofm("flac")
    if not args.ffargs:
        args.ffargs = argcheck_ffargs("-c:a flac -compression_level 8")

if args.preset == 12:
    # CD-Flac
    args.ofm = argcheck_ofm("flac")
    # downsampling can cause clipping, so limiting is applied before converting back to 16bit
    args.ffargs = argcheck_ffargs("-c:a flac -compression_level 8 -af aresample=osf=flt:osr=44100:resampler=swr:filter_type=kaiser,alimiter=limit=-0.1dB:level=off:attack=2.5:release=15,aresample=osf=s16:dither_method=triangular_hp")

def extract_coverart(in_filepath: Path, tempdir: Path) -> Path:
    '''
    @params
    @returns path_to_coverart
    '''

    if not args.alwayscover:
        # search for coverart in parent folder
        # the order of these names is respected and represents priorities
        iter_coverart_names = ('folder.jpg', 'folder.png',
                               'cover.jpg', 'cover.png',
                               'album.jpg', 'album.png',
                               'Thumb.jpg', 'AlbumArtSmall.jpg')
        for child in in_filepath.parent.iterdir():
            for cname in iter_coverart_names:
                cglob = child.glob(cname, case_sensitive=False)
                for cpath in cglob:
                    if cpath.exists():
                        return cpath

    # extract coverart from source if possible
    if in_filepath.exists() :
        cpath = Path(tempdir).joinpath(random_string(20) + '.jpg')
        cmd = [ Path(args.ffpath), '-y', '-i', Path(in_filepath) ]
        cmd.extend(["-map", "0:v", "-q:v", "5", cpath])
        if not args.vff:
            cmd.extend([ '-loglevel', 'fatal' ])
        if exec_cmd(cmd).returncode == 0:
            return cpath

    return None

def copy_file(in_filepath: Path, out_filepath: Path) -> Path:
    if args.fat:
        out_filepath = make_fat32_compatible(out_filepath)

    shutil.copyfile(in_filepath, out_filepath, follow_symlinks=False)

def convert_file(in_filepath: Path, out_filepath: Path) -> Path:
    if args.fat:
        out_filepath = make_fat32_compatible(out_filepath)

    ffargs = args.ffargs
    if args.preset == 4:
        #TODO move this to somewhere else, not as a preset
        # for normalisation we need to analyse the audio first
        cmd = [ Path(args.ffpath), '-y', '-i', Path(in_filepath) ]

        cmd.extend(["-map", "0:a", "-af", "ebur128", "-f", "wav"])
        cmd.append(os.devnull)
        ana_result = exec_cmd(cmd, output=subprocess.PIPE)
        ana_result = str(ana_result.stdout, "utf8")
        i_loudness = re.search(r"Integrated\sloudness\:\s+I\:\s+(\-\d+\.?\d*)", ana_result).groups()[0]
        i_loudrange = re.search(r"Loudness\srange\:\s+LRA\:\s+(\d+\.?\d*)", ana_result).groups()[0]

        # difference between target integrated LUFS and original vol
        # dynamic music will get a slight volume boost
        # ReplayGain and Spotify target is actually around -14LUFS or dB... after refactoring this should be customisable
        # -18LUFS is about the nominal of ReplayGain
        #gain_adjust = -18.0 - float(i_loudness) + (float(i_loudrange) * 0.25)
        gain_adjust = -18.0 - float(i_loudness)
        ffargs = argcheck_ffargs(" ".join(ffargs) + str(gain_adjust) + "dB")

    cmd = [ Path(args.ffpath), '-y', '-i', Path(in_filepath) ]
    if not args.vff:
        cmd.extend([ '-loglevel', 'error' ])
    cmd.extend(ffargs)
    cmd.append(Path(out_filepath))
    exec_cmd(cmd)

    # setup temporary directory for intermediary steps
with tempfile.TemporaryDirectory() as tempdir:
    # use thread queue for copying to ensure that long copy operations do not starve the conversion task pool
    with futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='copy') as copyexecutor:
        copy_tasks = set()
        # use threadpool for ffmpeg conversion as audio conversion is assumed to be singlethreaded 
        with futures.ThreadPoolExecutor(max_workers=args.max_workers, thread_name_prefix='converter') as convertexecutor:
            convert_tasks = set()

            # if you passed ignore_not_empty, we don't want to run into a loop and reconvert music we already converted
            if args.input_dir.resolve() == args.output_dir.resolve():
                pop_element_from_list(args.ifm, args.ofm)

            print("Starting conversion of folder {} to folder {}".format(args.input_dir, args.output_dir))
            print("Files with the endings {} will be converted to {}".format(str(args.ifm), args.ofm))
            print("Codec options to be passed to ffmpeg: ", str.join(' ', args.ffargs))
            print()

            for dirpath, dirnames, filenames in os.walk(args.input_dir):
                if args.v:
                    print("Currently evaluating directory " + dirpath)

                ignore_dir = str(args.ignore_dir)
                if ignore_dir != '.' and ignore_dir in dirpath:
                    # Skip directory that is meant to be ignored
                    continue

                out_dirpath = Path(args.output_dir, Path(dirpath).relative_to(args.input_dir))
                if args.fat:
                    out_dirpath = make_fat32_compatible(out_dirpath)

                out_dirpath.mkdir(exist_ok=True)

                currfolder_hascoverart = False
                for name in sorted(filenames):
                    in_filepath = Path(dirpath, name)
                    # Evaluate file
                    if name.lower().endswith(tuple(args.ifm)):
                        out_filepath = Path(out_dirpath, Path(name).stem + '.' + args.ofm)
                        convert_tasks.add(convertexecutor.submit(convert_file, in_filepath, out_filepath))
                        if not args.nocover and not currfolder_hascoverart:
                            coverpath = extract_coverart(in_filepath, tempdir)
                            if isinstance(coverpath, Path):
                                if args.v:
                                    print("  copying cover art " + str(coverpath) + " of " + str(name))
                                copy_tasks.add(copyexecutor.submit(copy_file, coverpath, Path(out_dirpath, "cover" + coverpath.suffix)))
                                currfolder_hascoverart = True
                    else:
                        if args.cfm == '*':
                            pass
                        elif name.lower().endswith(tuple(args.cfm)):
                            pass
                        elif nocopy:
                            # Copy file to destination
                            if args.v:
                                print("  copying file: " + str(name))
                            copy_tasks.add(copyexecutor.submit(copy_file, in_filepath, Path(out_dirpath, name)))

                    if not args.v:
                        print("{} files to copy, {} files to convert".format(len(copy_tasks), len(convert_tasks)), end='\r')

            print("\nFile evaluation finished")

            # show progress
            if not args.v:
                copies_completed = futures.as_completed(copy_tasks)
                converts_completed = futures.as_completed(convert_tasks)
                current_convert = 0
                for el in converts_completed:
                    current_convert += 1
                    print("{} out of {} files converted".format(current_convert, len(convert_tasks)), end='\r')

            print("\nCompleted")

