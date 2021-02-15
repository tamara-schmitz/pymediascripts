#!/usr/bin/python3

# Requires ffmpeg command!

import os
import shutil
from pathlib import Path
import textwrap
import argparse
import sys
import subprocess
import re
from concurrent import futures

def exec_cmd(cmd, output=None):
    if isinstance(cmd, str):
        cmd = cmd.split(' ')

    if sys.platform.startswith('win32'):
        # TODO this does not appear to work at this time
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.BELOW_NORMAL_PRIORITY_CLASS
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT, startupinfo=si)
    elif sys.platform.startswith('linux'):
        cmd.insert(0, "nice")
        cmd.insert(1, "-n19")
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)
    else:
        return subprocess.run(cmd, shell=False, stdout=output, stderr=subprocess.STDOUT)

# Argument custom validators
def argcheck_ifm(string):
    if_mask = tuple(string.strip().split(','))
    for el in if_mask:
        if not el.isalpha:
            print('Expected a list of file endings like: flac,wav,wave')
            raise argparse.ArgumentError()
    return if_mask
def argcheck_ofm(string):
    of_mask = string.strip()
    if not of_mask.isalpha:
        print('Expected a file ending like: ogg')
        raise argparse.ArgumentError()
    return of_mask
def argcheck_ffpath(string):
    ffpath = string.strip()
    if 'ffmpeg' not in ffpath:
        print('Expected a valid path or environment to ffmpeg like: ffmpeg')
        raise argparse.ArgumentError()
    return ffpath
def argcheck_ffargs(string):
    ffargs = string.strip().split(' ')
    if '-c:a' not in ffargs:
        print('Expected a valid audio codec string in \" like: \"-c:a libvorbis -q:a 7')
        raise argparse.ArgumentError()
    return ffargs

def argcheck_preset(string):
    if string == "smaller":
        return 1
    elif string == "compatible":
        return 2
    elif string == "dynamic_compressed":
        return 3
    elif string == "normalized":
        return 4
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
    parser.add_argument("--ignore-not-empty", type=Path, help="continue even if the output directory contains files. This overwrites existing files.")
    parser.add_argument("-ifm", "--inputfilemask", dest="ifm", default="flac,wav,aif,aiff,dsd", type=argcheck_ifm, help="Filter mask defining which files will be converted. Other files are copied")
    parser.add_argument("-ofm", "--outputformat", dest="ofm", default="ogg", type=argcheck_ofm, help="Output format of converted files")
    parser.add_argument("-ffpath", "--ffmpegpath", dest="ffpath", default="ffmpeg", type=argcheck_ffpath, help="Path to ffmpeg")
    parser.add_argument("-ffargs", "--ffmpegarguments", dest="ffargs", default="-map 0:v? -c:v libtheora -q:v 9 -map 0:a -c:a libvorbis -q:a 7", type=argcheck_ffargs, help="Codec options to submit to ffmpeg")
    parser.add_argument("-max_workers", default=os.cpu_count(), type=int, help="Set max parallel converter tasks. By default is your CPU thread count.")
    parser.add_argument("-v", "--verbose", dest="v", help="Verbose mode", action="store_true")
    parser.add_argument("-vff", "--verboseffmpeg", dest="vff", help="Verbose mode for ffmpeg", action="store_true")
    parser.add_argument("-p", "--preset", default="", type=argcheck_preset, help="Set a preset that overwrites other arguments. Possible values: smaller, compatible, dynamic_compressed, normalized")

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
    
# apply preset
if args.preset == 1:
    # smaller
    args.ofm = argcheck_ifm("ogg")
    args.ffargs = argcheck_ffargs("-map 0:v? -c:v libtheora -q:v 6 -map 0:a -c:a libopus -b:a 128k -vbr constrained")
    
if args.preset == 2:
    # compatible
    args.ofm = argcheck_ofm("mp3")
    args.ffargs = argcheck_ffargs("-c:a libmp3lame -b:a 320k")
    
if args.preset == 3:
    # dynamic_compressed
    args.ifm = argcheck_ifm("flac,wav,aif,aiff,dsd,mp3,wma,aac,m4a")
    args.ofm = argcheck_ofm("ogg")
    args.ffargs = argcheck_ffargs("-map 0:v? -c:v libtheora -q:v 9 -map 0:a " +
        " -metadata REPLAYGAIN_ALBUM_GAIN=0 -metadata REPLAYGAIN_ALBUM_PEAK=0.99" +
        " -metadata REPLAYGAIN_TRACK_GAIN=0 -metadata REPLAYGAIN_TRACK_PEAK=0.99" +
        "-c:a libopus -b:a 256k -vbr constrained -af aresample=osf=flt,dynaudnorm")
    
if args.preset == 4:
    # normalized
    args.ifm = argcheck_ifm("flac,wav,aif,aiff,dsd,mp3,wma,aac,m4a")
    args.ofm = argcheck_ofm("ogg")
    args.ffargs = argcheck_ffargs("-map 0:v? -c:v libtheora -q:v 9 -map 0:a " +
        " -metadata REPLAYGAIN_ALBUM_GAIN=0 -metadata REPLAYGAIN_ALBUM_PEAK=0.99" +
        " -metadata REPLAYGAIN_TRACK_GAIN=0 -metadata REPLAYGAIN_TRACK_PEAK=0.99" +
        "-c:a libopus -b:a 256k -vbr constrained -af aresample=osf=flt,alimiter=limit=-1.0dB:level=off:attack=5:release=25:level_in=")

def convert_file(in_filepath, out_filepath):
    ffargs = args.ffargs
    if args.preset == 4:
        #TODO move this to somewhere else, not as a preset
        # for normalisation we need to analyse the audio first
        cmd = [ Path(args.ffpath), '-y', '-i', in_filepath ]
        
        cmd.extend(["-map", "0:a", "-af", "ebur128", "-f", "wav"])
        cmd.append(os.devnull)
        ana_result = exec_cmd(cmd, output=subprocess.PIPE)
        ana_result = str(ana_result.stdout, "utf8")
        i_loudness = re.search("Integrated\sloudness\:\s+I\:\s+(\-\d+\.?\d*)", ana_result).groups()[0]
        i_loudrange = re.search("Loudness\srange\:\s+LRA\:\s+(\d+\.?\d*)", ana_result).groups()[0]
        
        # difference between target integrated LUFS and original vol
        # dynamic music will get lowered
        gain_adjust = -18.0 - float(i_loudness) - (float(i_loudrange) * 0.05)
        ffargs = argcheck_ffargs(" ".join(ffargs) + str(gain_adjust) + "dB")
        
    cmd = [ Path(args.ffpath), '-y', '-i', in_filepath ]
    if not args.vff:
        cmd.extend([ '-loglevel', 'error' ])
    cmd.extend(ffargs)
    cmd.append(out_filepath)
    if args.v:
        print("  Executing ffmpeg command: {}".format(cmd))
    exec_cmd(cmd)

# use threadpool for ffmpeg conversion as audio conversion is assumed to be singlethreaded 
with futures.ProcessPoolExecutor(max_workers=args.max_workers) as executor:
    print("Starting conversion of folder {} to folder {}".format(args.input_dir, args.output_dir))
    print("Files with the endings {} will be converted to {}".format(str(args.ifm), args.ofm))
    print("Codec options to be passed to ffmpeg: ", str.join(' ', args.ffargs))
    for dirpath, dirnames, filenames in os.walk(args.input_dir):
        if args.v:
            print("Currently evaluating directory " + str(dirpath))
            
        out_dirpath = Path(args.output_dir, Path(dirpath).relative_to(args.input_dir))
        out_dirpath.mkdir(exist_ok=True)
        for name in sorted(filenames):
            in_filepath = Path(dirpath, name)
            # Evaluate file
            if name.endswith(args.ifm):
                out_filepath = Path(out_dirpath, Path(name).stem + '.' + args.ofm)
                executor.submit(convert_file, in_filepath, out_filepath)
                    
            else:
                # Copy file to destination
                if args.v:
                    print("  Copying File: " + str(name))
            
                shutil.copyfile(in_filepath, Path(out_dirpath, name), follow_symlinks=False)
