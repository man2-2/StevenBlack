#!/usr/bin/env python

# Script by Ben Limmer
# https://github.com/l1m5
#
# This Python script will combine all the host files you provide
# as sources into one, unique host file to keep you internet browsing happy.

# pylint: disable=invalid-name
# pylint: disable=bad-whitespace

# Making Python 2 compatible with Python 3
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from glob import glob
import fnmatch
import argparse
import socket
import json
import zipfile

# zip files are not used actually, support deleted
# StringIO is not needed in Python 3
# Python 3 works differently with urlopen

try:                 # Python 3
    from urllib.parse import urlparse, urlencode
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
except ImportError:  # Python 2
    from urlparse import urlparse
    from urllib import urlencode
    from urllib2 import urlopen, Request, HTTPError

try:               # Python 2
    raw_input
except NameError:  # Python 3
    raw_input = input

# Detecting Python 3 for version-dependent implementations
Python3 = sys.version_info >= (3, 0)

# This function handles both Python 2 and Python 3
def getFileByUrl(url):
    try:
        f = urlopen(url)
        return f.read().decode("UTF-8")
    except:
        print("Problem getting file: ", url)
        # raise

# In Python 3   "print" is a function, braces are added everywhere

# Cross-python writing function
def writeData(f, data):
    if Python3:
        f.write(bytes(data, "UTF-8"))
    else:
        f.write(str(data).encode("UTF-8"))

# This function doesn't list hidden files
def listdir_nohidden(path):
    return glob(os.path.join(path, "*"))

# Project Settings
BASEDIR_PATH = os.path.dirname(os.path.realpath(__file__))

defaults = {
    "numberofrules" : 0,
    "datapath" : os.path.join(BASEDIR_PATH, "data"),
    "freshen" : True,
    "replace" : False,
    "backup" : False,
    "skipstatichosts": False,
    "keepdomaincomments": False,
    "extensionspath" : os.path.join(BASEDIR_PATH, "extensions"),
    "extensions" : [],
    "outputsubfolder" : "",
    "hostfilename" : "hosts",
    "targetip" : "0.0.0.0",
    "ziphosts" : False,
    "sourcedatafilename" : "update.json",
    "sourcesdata": [],
    "readmefilename" : "readme.md",
    "readmetemplate" : os.path.join(BASEDIR_PATH, "readme_template.md"),
    "readmedata" : {},
    "readmedatafilename" : os.path.join(BASEDIR_PATH, "readmeData.json"),
    "exclusionpattern" : "([a-zA-Z\d-]+\.){0,}",
    "exclusionregexs" : [],
    "exclusions" : [],
    "commonexclusions" : ["hulu.com"],
    "blacklistfile" : os.path.join(BASEDIR_PATH, "blacklist"),
    "whitelistfile" : os.path.join(BASEDIR_PATH, "whitelist")}

def main():

    parser = argparse.ArgumentParser(description="Creates a unified hosts file from hosts stored in data subfolders.")
    parser.add_argument("--auto", "-a", dest="auto", default=False, action="store_true", help="Run without prompting.")
    parser.add_argument("--backup", "-b", dest="backup", default=False, action="store_true", help="Backup the hosts files before they are overridden.")
    parser.add_argument("--extensions", "-e", dest="extensions", default=[], nargs="*", help="Host extensions to include in the final hosts file.")
    parser.add_argument("--ip", "-i", dest="targetip", default="0.0.0.0", help="Target IP address. Default is 0.0.0.0.")
    parser.add_argument("--keepdomaincomments", "-k", dest="keepdomaincomments", default=False, help="Keep domain line comments.")
    parser.add_argument("--zip", "-z", dest="ziphosts", default=False, action="store_true", help="Additionally create a zip archive of the hosts file.")
    parser.add_argument("--noupdate", "-n", dest="noupdate", default=False, action="store_true", help="Don't update from host data sources.")
    parser.add_argument("--skipstatichosts", "-s", dest="skipstatichosts", default=False, action="store_true", help="Skip static localhost entries in the final hosts file.")
    parser.add_argument("--output", "-o", dest="outputsubfolder", default="", help="Output subfolder for generated hosts file.")
    parser.add_argument("--replace", "-r", dest="replace", default=False, action="store_true", help="Replace your active hosts file with this new hosts file.")
    parser.add_argument("--flush-dns-cache", "-f", dest="flushdnscache", default=False, action="store_true", help="Attempt to flush DNS cache after replacing the hosts file.")

    global  settings

    options = vars(parser.parse_args())

    options["outputpath"] = os.path.join(BASEDIR_PATH, options["outputsubfolder"])
    options["freshen"] = not options["noupdate"]

    settings = {}
    settings.update(defaults)
    settings.update(options)

    settings["sources"] = listdir_nohidden(settings["datapath"])
    settings["extensionsources"] = listdir_nohidden(settings["extensionspath"])

    # All our extensions folders...
    settings["extensions"] = [os.path.basename(item) for item in listdir_nohidden(settings["extensionspath"])]
    # ... intersected with the extensions passed-in as arguments, then sorted.
    settings["extensions"]  = sorted( list(set(options["extensions"]).intersection(settings["extensions"])) )

    with open(settings["readmedatafilename"], "r") as f:
        settings["readmedata"] = json.load(f)

    promptForUpdate()
    promptForExclusions()
    mergeFile = createInitialFile()
    removeOldHostsFile()
    finalFile = removeDupsAndExcl(mergeFile)
    finalizeFile(finalFile)

    if settings["ziphosts"]:
        zf = zipfile.ZipFile(os.path.join(settings["outputsubfolder"], "hosts.zip"), mode='w')
        zf.write(os.path.join(settings["outputsubfolder"], "hosts"), compress_type=zipfile.ZIP_DEFLATED, arcname='hosts')
        zf.close()

    updateReadmeData()
    printSuccess("Success! The hosts file has been saved in folder " + settings["outputsubfolder"] + "\nIt contains " +
                 "{:,}".format(settings["numberofrules"]) + " unique entries.")

    promptForMove(finalFile)


# Prompt the User
def promptForUpdate():
    # Create hosts file if it doesn't exists
    if not os.path.isfile(os.path.join(BASEDIR_PATH, "hosts")):
        try:
            open(os.path.join(BASEDIR_PATH, "hosts"), "w+").close()
        except:
            printFailure("ERROR: No 'hosts' file in the folder,"
                         "try creating one manually")

    if not settings["freshen"]:
        return

    prompt = "Do you want to update all data sources?"
    if settings["auto"] or query_yes_no(prompt):
        updateAllSources()
    elif not settings["auto"]:
        print("OK, we'll stick with what we've  got locally.")


def promptForExclusions():
    prompt = ("Do you want to exclude any domains?\n"
              "For example, hulu.com video streaming must be able to access "
              "its tracking and ad servers in order to play video.")

    if not settings["auto"]:
        if query_yes_no(prompt):
            displayExclusionOptions()
        else:
            print("OK, we'll only exclude domains in the whitelist.")


def promptForFlushDnsCache():
    if settings["flushdnscache"]:
        flush_dns_cache()

    if not settings["auto"]:
        if query_yes_no("Attempt to flush the DNS cache?"):
            flush_dns_cache()


def promptForMove(finalFile):
    if settings["replace"] and not settings["skipstatichosts"]:
        move_file = True
    elif settings["auto"] or settings["skipstatichosts"]:
        move_file = False
    else:
        prompt = ("Do you want to replace your existing hosts file " +
                  "with the newly generated file?")
        move_file = query_yes_no(prompt)

    if move_file:
        move_hosts_file_into_place(finalFile)
        promptForFlushDnsCache()
    else:
        return False
# End Prompt the User


# Exclusion logic
def displayExclusionOptions():
    for exclusionOption in settings["commonexclusions"]:
        prompt = "Do you want to exclude the domain " + exclusionOption + " ?"

        if query_yes_no(prompt):
            excludeDomain(exclusionOption)
        else:
            continue

    if query_yes_no("Do you want to exclude any other domains?"):
        gather_custom_exclusions()


def gather_custom_exclusions():
    """
    Gather custom exclusions from the user.
    """

    # We continue running this while-loop until the user
    # says that they have no more domains to exclude.
    while True:
        domain_prompt = ("Enter the domain you want "
                         "to exclude (e.g. facebook.com): ")
        user_domain = raw_input(domain_prompt)

        if isValidDomainFormat(user_domain):
            excludeDomain(user_domain)

        continue_prompt = "Do you have more domains you want to enter?"
        if not query_yes_no(continue_prompt):
            return


def excludeDomain(domain):
    settings["exclusionregexs"].append(re.compile(settings["exclusionpattern"] + domain))

def matchesExclusions(strippedRule):
    strippedDomain = strippedRule.split()[1]
    for exclusionRegex in settings["exclusionregexs"]:
        if exclusionRegex.search(strippedDomain):
            return True
    return False
# End Exclusion Logic

# Update Logic
def updateAllSources():
    # Update all hosts files regardless of folder depth
    # allsources = glob('*/**/' + settings["sourcedatafilename"], recursive=True)
    allsources = recursiveGlob("*", settings["sourcedatafilename"])
    for source in allsources:
        updateFile = open(source, "r")
        updateData = json.load(updateFile)
        updateURL  = updateData["url"]
        updateFile.close()

        print("Updating source " + os.path.dirname(source) + " from " + updateURL)
        # Cross-python call
        updatedFile = getFileByUrl(updateURL)
        try:
            updatedFile = updatedFile.replace("\r", "") #get rid of carriage-return symbols

            # This is cross-python code
            hostsFile = open(os.path.join(BASEDIR_PATH, os.path.dirname(source), settings["hostfilename"]), "wb")
            writeData(hostsFile, updatedFile)
            hostsFile.close()
        except:
            print("Skipping.")
# End Update Logic

# File Logic
def createInitialFile():
    mergeFile = tempfile.NamedTemporaryFile()

    # spin the sources for the base file
    for source in recursiveGlob(settings["datapath"], settings["hostfilename"]):
        with open(source, "r") as curFile:
            #Done in a cross-python way
            writeData(mergeFile, curFile.read())

    for source in recursiveGlob(settings["datapath"], settings["sourcedatafilename"]):
        updateFile = open(source, "r")
        updateData = json.load(updateFile)
        settings["sourcesdata"].append(updateData)
        updateFile.close()

    # spin the sources for extensions to the base file
    for source in settings["extensions"]:
        # filename = os.path.join(settings["extensionspath"], source, settings["hostfilename"])
        for filename in recursiveGlob(os.path.join(settings["extensionspath"], source), settings["hostfilename"]):
            with open(filename, "r") as curFile:
                #Done in a cross-python way
                writeData(mergeFile, curFile.read())

        # updateFilePath = os.path.join(settings["extensionspath"], source, settings["sourcedatafilename"])
        for updateFilePath in recursiveGlob( os.path.join(settings["extensionspath"], source), settings["sourcedatafilename"]):
            updateFile = open(updateFilePath, "r")
            updateData = json.load(updateFile)
            settings["sourcesdata"].append(updateData)
            updateFile.close()

    if os.path.isfile(settings["blacklistfile"]):
        with open(settings["blacklistfile"], "r") as curFile:
            #Done in a cross-python way
            writeData(mergeFile, curFile.read())

    return mergeFile

def removeDupsAndExcl(mergeFile):
    numberOfRules = settings["numberofrules"]
    if os.path.isfile(settings["whitelistfile"]):
        with open(settings["whitelistfile"], "r") as ins:
            for line in ins:
                line = line.strip(" \t\n\r")
                if line and not line.startswith("#"):
                    settings["exclusions"].append(line)

    if not os.path.exists(settings["outputpath"]):
        os.makedirs(settings["outputpath"])

    # Another mode is required to read and write the file in Python 3
    finalFile = open(os.path.join(settings["outputpath"], "hosts"),
                     "w+b" if Python3 else "w+")

    mergeFile.seek(0) # reset file pointer
    hostnames = set(["localhost", "localhost.localdomain", "local", "broadcasthost"])
    exclusions = settings["exclusions"]
    for line in mergeFile.readlines():
        write = "true"
        # Explicit encoding
        line = line.decode("UTF-8")
        # replace tabs with space
        line = line.replace("\t+", " ")
        # Trim trailing whitespace, periods -- (Issue #271 - https://github.com/StevenBlack/hosts/issues/271)
        line = line.rstrip(' .') + "\n"
        # Testing the first character doesn't require startswith
        if line[0] == "#" or re.match(r'^\s*$', line[0]):
            # Cross-python write
            writeData(finalFile, line)
            continue
        if "::1" in line:
            continue

        strippedRule = stripRule(line) #strip comments
        if not strippedRule or matchesExclusions(strippedRule):
            continue
        hostname, normalizedRule = normalizeRule(strippedRule) # normalize rule
        for exclude in exclusions:
            if exclude in line:
                write = "false"
                break
        if normalizedRule and (hostname not in hostnames) and (write == "true"):
            writeData(finalFile, normalizedRule)
            hostnames.add(hostname)
            numberOfRules += 1

    settings["numberofrules"] = numberOfRules
    mergeFile.close()

    return finalFile

def normalizeRule(rule):
    result = re.search(r'^[ \t]*(\d+\.\d+\.\d+\.\d+)\s+([\w\.-]+)(.*)', rule)
    if result:
        hostname, suffix = result.group(2,3)
        hostname = hostname.lower().strip() # explicitly lowercase and trim the hostname
        if suffix and settings["keepdomaincomments"]:
            # add suffix as comment only, not as a separate host
            return hostname, "%s %s #%s\n" % (settings["targetip"], hostname, suffix)
        else:
            return hostname, "%s %s\n" % (settings["targetip"], hostname)
    print("==>%s<==" % rule)
    return None, None

def finalizeFile(finalFile):
    writeOpeningHeader(finalFile)
    finalFile.close()

# Some sources put comments around their rules, for accuracy we need to strip them
# the comments are preserved in the output hosts file
def stripRule(line):
    splitLine = line.split()
    if len(splitLine) < 2 :
        # just return blank
        return ""
    else:
        return splitLine[0] + " " + splitLine[1]

def writeOpeningHeader(finalFile):
    finalFile.seek(0) #reset file pointer
    fileContents = finalFile.read()  #save content
    finalFile.seek(0) #write at the top
    writeData(finalFile, "# This hosts file is a merged collection of hosts from reputable sources,\n")
    writeData(finalFile, "# with a dash of crowd sourcing via Github\n#\n")
    writeData(finalFile, "# Date: " + time.strftime("%B %d %Y", time.gmtime()) + "\n")
    if settings["extensions"]:
        writeData(finalFile, "# Extensions added to this file: " + ", ".join(settings["extensions"]) + "\n")
    writeData(finalFile, "# Number of unique domains: " + "{:,}\n#\n".format(settings["numberofrules"]))
    writeData(finalFile, "# Fetch the latest version of this file: https://raw.githubusercontent.com/StevenBlack/hosts/master/"+ os.path.join(settings["outputsubfolder"],"") + "hosts\n")
    writeData(finalFile, "# Project home page: https://github.com/StevenBlack/hosts\n#\n")
    writeData(finalFile, "# ===============================================================\n")
    writeData(finalFile, "\n")

    if not settings["skipstatichosts"]:
        writeData(finalFile, "127.0.0.1 localhost\n")
        writeData(finalFile, "127.0.0.1 localhost.localdomain\n")
        writeData(finalFile, "127.0.0.1 local\n")
        writeData(finalFile, "255.255.255.255 broadcasthost\n")
        writeData(finalFile, "::1 localhost\n")
        writeData(finalFile, "fe80::1%lo0 localhost\n")
        writeData(finalFile, "0.0.0.0 0.0.0.0\n")
        if platform.system() == "Linux":
            writeData(finalFile, "127.0.1.1 " + socket.gethostname() + "\n")
            writeData(finalFile, "127.0.0.53 " + socket.gethostname() + "\n")
        writeData(finalFile, "\n")

    preamble = os.path.join(BASEDIR_PATH, "myhosts")
    if os.path.isfile(preamble):
        with open(preamble, "r") as f:
            writeData(finalFile, f.read())

    finalFile.write(fileContents)

def updateReadmeData():
    extensionsKey = "base"
    hostsLocation = ""
    if settings["extensions"]:
        extensionsKey = "-".join(settings["extensions"])

    generationData = {"location": os.path.join(settings["outputsubfolder"], ""),
                      "entries": settings["numberofrules"],
                      "sourcesdata": settings["sourcesdata"]}
    settings["readmedata"][extensionsKey] = generationData
    with open(settings["readmedatafilename"], "w") as f:
        json.dump(settings["readmedata"], f)


def move_hosts_file_into_place(final_file):
    """
    Move the newly-created hosts file into its correct location on the OS.
    For UNIX systems, the hosts file is "etc/hosts." On Windows, it's
    "C:\Windows\system32\drivers\etc\hosts."
    For this move to work, you must have administrator privileges to do this.
    On UNIX systems, this means having "sudo" access, and on Windows, it
    means being able to run command prompt in administrator mode.

    Parameters
    ----------
    final_file : str
        The name of the newly-created hosts file to move.
    """

    filename = os.path.abspath(final_file.name)

    if os.name == "posix":
        print("Moving the file requires administrative privileges. "
              "You might need to enter your password.")
        if subprocess.call(["/usr/bin/sudo", "cp", filename, "/etc/hosts"]):
            printFailure("Moving the file failed.")
    elif os.name == "nt":
        print("Automatically moving the hosts file "
              "in place is not yet supported.")
        print("Please move the generated file to "
              "%SystemRoot%\system32\drivers\etc\hosts")


def flush_dns_cache():
    """
    Flush the DNS cache.
    """

    print("Flushing the DNS cache to utilize new hosts file...")
    print("Flushing the DNS cache requires administrative privileges. " +
          "You might need to enter your password.")

    dns_cache_found = False

    if platform.system() == "Darwin":
        if subprocess.call(["/usr/bin/sudo", "killall",
                            "-HUP", "mDNSResponder"]):
            printFailure("Flushing the DNS cache failed.")
    elif os.name == "nt":
        print("Automatically flushing the DNS cache is not yet supported.")
        print("Please copy and paste the command 'ipconfig /flushdns' in "
              "command prompt after running this script.")
    else:
        if os.path.isfile("/etc/rc.d/init.d/nscd"):
            dns_cache_found = True

            if subprocess.call(["/usr/bin/sudo", "/etc/rc.d/init.d/nscd",
                                "restart"]):
                printFailure("Flushing the DNS cache failed.")
            else:
                printSuccess("Flushing DNS by restarting nscd succeeded")

        if os.path.isfile("/usr/lib/systemd/system/NetworkManager.service"):
            dns_cache_found = True

            if subprocess.call(["/usr/bin/sudo", "/usr/bin/systemctl",
                                "restart", "NetworkManager.service"]):
                printFailure("Flushing the DNS cache failed.")
            else:
                printSuccess("Flushing DNS by restarting "
                             "NetworkManager succeeded")

        if os.path.isfile("/usr/lib/systemd/system/wicd.service"):
            dns_cache_found = True

            if subprocess.call(["/usr/bin/sudo", "/usr/bin/systemctl",
                                "restart", "wicd.service"]):
                printFailure("Flushing the DNS cache failed.")
            else:
                printSuccess("Flushing DNS by restarting wicd succeeded")

        if os.path.isfile("/usr/lib/systemd/system/dnsmasq.service"):
            dns_cache_found = True

            if subprocess.call(["/usr/bin/sudo", "/usr/bin/systemctl",
                                "restart", "dnsmasq.service"]):
                printFailure("Flushing the DNS cache failed.")
            else:
                printSuccess("Flushing DNS by restarting dnsmasq succeeded")

        if os.path.isfile("/usr/lib/systemd/system/networking.service"):
            dns_cache_found = True

            if subprocess.call(["/usr/bin/sudo", "/usr/bin/systemctl",
                                "restart", "networking.service"]):
                printFailure("Flushing the DNS cache failed.")
            else:
                printSuccess("Flushing DNS by restarting "
                             "networking.service succeeded")

        if not dns_cache_found:
            printFailure("Unable to determine DNS management tool.")


def removeOldHostsFile():               # hotfix since merging with an already existing hosts file leads to artefacts and duplicates
    oldFilePath = os.path.join(BASEDIR_PATH, "hosts")
    open(oldFilePath, "a").close()        # create if already removed, so remove wont raise an error

    if settings["backup"]:
        backupFilePath = os.path.join(BASEDIR_PATH, "hosts-{}".format(time.strftime("%Y-%m-%d-%H-%M-%S")))
        shutil.copy(oldFilePath, backupFilePath) # make a backup copy, marking the date in which the list was updated

    os.remove(oldFilePath)
    open(oldFilePath, "a").close()        # create new empty hostsfile


# End File Logic

# Helper Functions
def query_yes_no(question, default="yes"):
    """
    Ask a yes/no question via raw_input() and get answer from the user.

    Inspired by the following implementation:

    http://code.activestate.com/recipes/577058

    Parameters
    ----------
    question : str
        The question presented to the user.
    default : str, default "yes"
        The presumed answer if the user just hits <Enter>. It must be "yes",
        "no", or None (means an answer is required of the user).

    Returns
    -------
    yes : Whether or not the user replied yes to the question.
    """

    valid = {"yes": "yes", "y": "yes", "ye": "yes",
             "no": "no", "n": "no"}
    prompt = {None: " [y/n] ",
              "yes": " [Y/n] ",
              "no": " [y/N] "}.get(default, None)

    if not prompt:
        raise ValueError("invalid default answer: '%s'" % default)

    reply = None

    while not reply:
        sys.stdout.write(colorize(question, colors.PROMPT) + prompt)

        # Changed to be cross-python
        choice = raw_input().lower()
        reply = None

        if default and not choice:
            reply = default
        elif choice in valid:
            reply = valid[choice]
        else:
            printFailure("Please respond with 'yes' or 'no' "
                         "(or 'y' or 'n').\n")

    return reply == "yes"


def isValidDomainFormat(domain):
    if domain == "":
        print("You didn't enter a domain. Try again.")
        return False
    domainRegex = re.compile("www\d{0,3}[.]|https?")
    if domainRegex.match(domain):
        print("The domain " + domain +
              " is not valid. Do not include "
              "www.domain.com or http(s)://domain.com. Try again.")
        return False
    else:
        return True

# A version-independent glob(  ... "/**/" ... )
def recursiveGlob(stem, filepattern):
    if sys.version_info >= (3,5):
        return glob(stem + "/**/" + filepattern, recursive=True)
    else:
        if stem == "*":
            stem = "."
        matches = []
        for root, dirnames, filenames in os.walk(stem):
            for filename in fnmatch.filter(filenames, filepattern):
                matches.append(os.path.join(root, filename))
    return matches


# Colors
class colors:
    PROMPT  = "\033[94m"
    SUCCESS = "\033[92m"
    FAIL    = "\033[91m"
    ENDC    = "\033[0m"

def colorize(text, color):
    return color + text + colors.ENDC

def printSuccess(text):
    print(colorize(text, colors.SUCCESS))

def printFailure(text):
    print(colorize(text, colors.FAIL))
# End Helper Functions

if __name__ == "__main__":
    main()
