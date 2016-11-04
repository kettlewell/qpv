#!/usr/bin/env python
'''
qpv - quick photo view
'''

qpvVersion = 1.3

import sys
import math
import string

#import io  # new in version 2.6 !
import os
import subprocess
import urllib
import codecs
import random

import webbrowser
from datetime import datetime
import wx
import wx.lib.anchors as anchors

if sys.version_info.major == 2:
   if sys.version_info.minor == 7:
      print 'IMPORT: PYTHON version 2.7 as expected'
   else:
      print 'IMPORT: PYTHON version 2.x not quite as expected, might work'
else:
   print 'IMPORT: PYTHON version not expected: ' + str(sys.version_info.major)

if wx.VERSION[0] == 3:
   if wx.VERSION[1] == 0:
      print 'IMPORT: WXPYTHON version 3.0 as expected'
   else:
      print 'IMPORT: WXPYTHON version 3.x not quite as expected, might work'
else:
   print 'IMPORT: WXPYTHON version not expected: ' + str(wx.VERSION[0])

hasPIL = False
hasChiffre = False

# experiment = True

try:
   from PIL import Image           # for EXIF data
   from PIL.ExifTags import TAGS
   print "IMPORT: PIL available, EXIF tags will work"
   hasPIL = True
except ImportError:
   print "IMPORT: PIL not available, no EXIF tags. Try pip install PIL"
   hasPIL = False

try:
   from leware import cchiffre  # cchiffre is the C version, much faster
   chiffreEnv = os.environ.get('CHIFFRE')
   if chiffreEnv == None:
      hasChiffre = False
   else:
      hasChiffre = True
      print "IMPORT: leware.cchiffre available, CHIFFRE provided"
except ImportError:
   print "IMPORT: Unable to import leware.cchiffre. try pip install leware ?"
   chiffreEnv = None
   hasChiffre = False

image_editor = os.environ.get('IMAGE_EDITOR')

local_encoding = os.environ.get('LPV_ENCODING')
if local_encoding == None:
   local_encoding = 'utf-8' # defaults to what I use, feel free to change
   # or maybe could use locale.getpreferredencoding()

try:
   from cStringIO import StringIO
except ImportError:
   print "IMPORT: cStringIO not found, using StringIO instead"
   from StringIO import StringIO

caseSensitive = False  # eg. Windows, MacOS

if os.name == 'posix' and sys.platform.lower() != 'darwin':    # was os.uname()[0].
   caseSensitive = True
   print 'FILE NAMES are case-sensitive'

def local2uni(str):
   global local_encoding

   if type(str) is unicode:
      return str
   else:
      return str.decode(local_encoding, 'ignore')  # TBD: do I want 'ignore' here? possibly not

def utf2uni(str):

   if type(str) is unicode:
      return str
   else:
      return str.decode('utf-8', 'ignore')  # TBD: do I want 'ignore' here? probably (it's just an experiment)

def unicode2uni(str):  # for exif UserComment field
   return str.decode('utf_16_be', 'ignore')

def printable(str):     # printing problems occur when stdout goes to file rather than terminal; it is then 'ascii' and not tolerant
   global local_encoding

   if not type(str) is unicode:
      return str.decode(local_encoding, 'ignore').encode(local_encoding, 'replace')
   else:
      return str.encode(local_encoding, 'replace')

currDir = os.getcwd().replace('\\', '/')
pythDir = os.path.dirname(os.path.realpath(__file__)).replace('\\', '/') + '/'
if os.path.isdir(utf2uni(currDir)):
   currDir = utf2uni(currDir)
else:
   currDir = local2uni(currDir)
if os.path.isdir(utf2uni(pythDir)):
   pythDir = utf2uni(pythDir)
else:
   pythDir = local2uni(pythDir)
imageDir=pythDir + 'images/'
print 'WORKING DIR: ' + printable(currDir) , '\nAPPLICATION DIR: ' + printable(pythDir), '\nIMAGE DIR: ' + printable(imageDir)

def normaliseFileName(name, givenDir=None):     # assumes unicode
   global currDir

   if name == None:
      return None

   # if name.startswith('http://') or name.startswith('https://'):
   #    return name

   name = name.replace(u'\\', u'/')

   absolute = False

   if name.startswith(u'/'):
      absolute = True
   elif name[1:3] == u':/' and u'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'.find(name[0:1]) >= 0:
      absolute = True

   if not absolute:
      if givenDir != None:
         name = givenDir + u'/' + name
      else:
         name = currDir + u'/' + name

   while name.find(u'//') >= 0:
      ix = name.find(u'//')
      name = name[0:ix] + name[ix+1:]

   while name.find(u'/./') >= 0:
      ix = name.find(u'/./')
      name = name[0:ix] + name[ix+2:]

   while name.find(u'/../') >= 0:
      ix = name.find(u'/../')
      jx = ix

      while jx > 0:
         jx -= 1
         if name[jx] == u'/':
            break

      name = name[0:jx] + name[ix+3:]

   return name

def compareText(fn1, fn2, insensitive=None):
   if insensitive == None and not caseSensitive:
      fn1 = fn1.lower()
      fn2 = fn2.lower()
   elif insensitive == True:
      fn1 = fn1.lower()
      fn2 = fn2.lower()

   if fn1 == fn2:
      return 0
   elif fn1 < fn2:
      return -1
   else:
      return 1

imageSuffixes = [u'.jpg', u'.jpeg', u'.gif', u'.png', u'.tif', u'.tiff', u'.bmp']
textSuffixes = [u'.lpv']  # removed .txt option

couldNotFind = 0
couldNotFindNames = u""
lastError = None

                                 # TBD: dirWalk seems backwards in semantics
def processParameterTry(parm, recursion=0, dirWalk=False, directory=None, checkFile=True):
   added = 0

   if parm.startswith('http://') or parm.startswith('https://'):
      addedImage = ImageHook.findImage(parm)
      if addedImage == None:
         addedImage = ImageHook(parm, 0x24137777, len(parm))
         ImageHook.addImage(addedImage)
      if addedImage != None and ImageHook.newest == None:
         ImageHook.newest = addedImage
      added += 1   # +1 even if already there
      return added

   parm = normaliseFileName(parm.strip(), directory)

   if os.path.isdir(parm):
      # print 'DIR: ' + printable(parm)
      if not dirWalk:
         # print 'WALKING DIRECTORY ' + printable(parm)
         files = os.listdir(parm)
         for f in files:
            added += processParameterTry(parm + u'/' + f, recursion+3, True)   # processParameterTry() ?

   else:
      ftime = 1147  # marker for checkFile == False
      flength = 0
      if checkFile:
         if os.path.isfile(parm):
            # print 'FIL: ' + printable(parm)
            info = os.stat(parm)
            ftime = info.st_mtime
            flength = info.st_size
         else:
            return added    # adding to couldNotFind* done below
      else:
         pass
         # print 'fil: ' + printable(parm)  # unchecked

      extIx = parm.rfind(u'.')

      if extIx > 0:
         suffix = parm[extIx:].lower()

         if suffix in textSuffixes:
            # print '  text'
            if not dirWalk:
               extIx = parm.rfind(u'/')
               if extIx >= 0:
                  refDir = parm[0:extIx+1]
               else:
                  refDir = u'/NO/REFERENCE/DIRECTORY!/'
               # print printable(u'WALKING TEXT FILE, refDir=' + refDir)

               f = open(parm, 'rt')     # TBD open to automatically read Unicode or not?
               willCheckFile = True
               lastAddedValid = False
               unicode = False
               smartNotes = False       # TBD: CI on this code
               smartDict = {}
               smartName = None

               # TBD: needs to be made unicode-savvy  http://stackoverflow.com/questions/491921/unicode-utf8-reading-and-writing-to-files-in-python
               for line in f:
                  if line.startswith('_'):
                     line = line[3:]
                     unicode = True
                     # print '   unicode=True'
                  if len(line) > 1 and line[0] != ' ' and line[0] != '#':
                     if unicode:
                        line = line.decode('utf-8').strip()
                     else:
                        line = local2uni(line).strip()
                     ix = line.rfind('/')
                     if ix < 0:
                        ix = line.rfind('\\')
                     smartName = line[ix+1:]
                     toAdd = processParameterTry(line, recursion+3, dirWalk, refDir, willCheckFile)  # processParameter() ?
                     added += toAdd
                     if toAdd == 1 and smartName == ImageHook.current.simpleFileName:     # could run into trouble with just first test, eg, if line is *.lpv file with 1 image?
                        lastAddedValid = True
                        if smartName in smartDict and ImageHook.current.notes == u'':
                           ImageHook.current.notes = smartDict[smartName]
                     else:
                        lastAddedValid = False
                  elif line.startswith('  (deletable)'):
                     if lastAddedValid:
                         ImageHook.current.deletable = True;
                  elif line.startswith('  (marked)'):
                     if lastAddedValid:
                         ImageHook.current.marked = True;
                  elif line.startswith('  Date='):
                     pass
                  elif len(line) > 8 and line.startswith('  Notes='):
                     notes = line[8:].strip()
                     if unicode:
                        notes = notes.decode('utf-8')
                     else:
                        notes = local2uni(notes)
                     if lastAddedValid:
                        ImageHook.current.notes = notes
                        lastAddedValid = False
                     if smartNotes and smartName != None:
                        smartDict[smartName] = notes
                        smartName = None
                  elif line.startswith('# NO_CHECK_FILE'):
                     lastAddedValid = False
                     smartName = None
                     willCheckFile = False
                  elif line.startswith('# CRASH_LPV'):
                     processParameter(someUndefinedVariable, recursion+3, dirWalk, refDir, willCheckFile)
                  elif line.startswith('# SMART_NOTES'):
                     global couldNotFind, couldNotFindNames    # toggles this mode, can be used at end to cleanup list
                     couldNotFind = 0
                     couldNotFindNames = u""
                     smartNotes = not smartNotes
                  else:
                     lastAddedValid = False
                     smartName = None
               f.close()

               # removing temporarily -- see also re-ordering of tests on initial processing of pps
               # if added > 0:       # TBD: wozu?
               #    added += 1

         elif suffix in imageSuffixes:
            # print '  image ' + datetime.fromtimestamp(ftime).strftime('%Y-%m-%d %H:%M')
            addedImage = ImageHook.findImage(parm)
            if addedImage == None:
               addedImage = ImageHook(parm, ftime, flength)
               ImageHook.addImage(addedImage)
            if addedImage != None and ImageHook.newest == None:
               ImageHook.newest = addedImage
            added += 1   # +1 even if already there

         else:
            pass
            # print '  ignoring '

   return added

def processParameter(parm, recursion=0, dirWalk=False, directory=None, checkFile=True):
   global couldNotFind, couldNotFindNames
   parmU = local2uni(parm)
   if parmU.endswith('/LpvWx.py'):      # MacOS
      return 0
   added = processParameterTry(parmU, recursion, dirWalk, directory, checkFile)
   if added ==  0:
      parmU = utf2uni(parm)  # alternate decoding to try, helps on Mac
      added = processParameterTry(parmU, recursion, dirWalk, directory, checkFile)
      if added == 0:
         couldNotFind += 1
         if couldNotFind == 1:
            couldNotFindNames = u"# MISSING (could not find image or no image in directory):\n# " + parm + u"\n"
         else:
            couldNotFindNames += u"# " + parm + u"\n"
         print 'Could not find file: ' + printable(parm)
   return added

# functions used to read orientation when module PIL not available

def readShort(ba, ix, right):  # byte array, index, endianness
   if right:    # right-endian (aka big-endian)
      return (ba[ix+1] & 0xff) | ((ba[ix] & 0xff) << 8)
   else:
      return (ba[ix] & 0xff) | ((ba[ix+1] & 0xff) << 8)

def checkHeader(ba, ix, bat):  # byte array, index, template
   lgt = len(ba) - ix
   if lgt > len(bat):
      for k in xrange(len(bat)):
         if bat[k] != 0x77:
            if ba[k+ix] != bat[k]:
               return False
      return True
   return False

def readOrientation(ba, ix, right):  # byte array, index, endianness
   n = readShort(ba, ix, right)
   ix += 2
   for k in xrange(n):
      if ix > len(ba) - 10:
         return -1  # not found
      tag = readShort(ba, ix, right)
      typ = readShort(ba, ix+2, right)
      # print 'tag=', tag, 'type=', typ
      if tag == 0x112 and typ == 0x03:
         val = readShort(ba, ix+8, right)
         # print 'val=', val, 'ix=', ix
         return val
      ix += 12
   return -1  # not found

exifTiffIntel = bytearray([0xff, 0xe1, 0x77, 0x77, 0x45, 0x78, 0x69, 0x66, 0x00, 0x00, 0x49, 0x49, 0x2A, 0x00, 0x08, 0x00, 0x00, 0x00])
exifTiffMoto  = bytearray([0xff, 0xe1, 0x77, 0x77, 0x45, 0x78, 0x69, 0x66, 0x00, 0x00, 0x4d, 0x4d, 0x00, 0x2a, 0x00, 0x00, 0x00, 0x08])

# REMOVE FOLLOWING BLOCK
# for p in sys.argv[1:]:
#    print 'PROCESSING ' + p
#    print 'ADDED ' + str(processParameter(p))
# print 'FINAL LIST'
# for p in tempList:
#    print p
# print couldNotFindNames
# quit()

class SortStatus:
   unsorted       = 0
   sortedDate     = 1
   sortedName     = 2
   sortedFlags    = 3
   sortedNotes    = 4
   sortedFullName = 5
   sortedSize     = 6

usefulSorts = [SortStatus.sortedDate, SortStatus.sortedNotes, SortStatus.sortedFullName, SortStatus.sortedSize] # see significantChange() below

class ImageHook:

   current = None  # class variable -- see someVar.py here
   newest = None   # when opening / re-opening images
   sortStatus = SortStatus.unsorted

   marked = False  # class variable, becomes instance var if  self.marked =
   deletable = False

   exifMetadata = '  No EXIF meta data available\n'  # will usually be overridden by instance

   sonderbar = False     # these often stay at their defaults
   greyscale = False
   notes = u''
   selector = 0.0
   exifDate = None
   gamma = 100
   click = (-1.0, -1.0)  # related to image without global rotation

   def __init__(self, name, date, size):
      self.fullFileName = name
      extIx = name.rfind('/')
      self.simpleFileName = name[extIx+1:]
      self.fileDate = date
      self.fileSize = size
      self.rotation = 360       # unknown
      if caseSensitive:
         self.sortKey = ('%08x' % date) + '-' + self.simpleFileName + '-' + ('%08x' % date)
      else:
         self.sortKey = ('%08x' % date) + '-' + self.simpleFileName.lower() + '-' + ('%08x' % date)
      # TBD: why did I instancialize them?
      # self.notes = u''
      # self.selector = 0.0
      # click = (-1.0, -1.0)

      self.height = self.width = 0    # zero means file not yet seen

      # print 'Instanciated file ' + name + ', sortKey=' + self.sortKey

   @staticmethod
   def findImage(path):
      hicker = ImageHook.current
      if hicker != None:
         if compareText(path, hicker.fullFileName) == 0:
            return hicker
         while hicker.prev != None:
            hicker = hicker.prev
            if compareText(path, hicker.fullFileName) == 0:
               return hicker
         hicker = ImageHook.current
         while hicker.next != None:
            hicker = hicker.next
            if compareText(path, hicker.fullFileName) == 0:
               return hicker

      return None

      #   name = name.lower()
      #   if name in map(lambda x: x.lower(), tempList):   # less sexy: if name.lower() in (n.lower() for n in tempList):
      #      return name

   @staticmethod
   def countImages():  # returns a tuple
      global couldNotFind
      hicker = ImageHook.current
      count = 0
      countMarked = 0
      countDeletable = 0
      if hicker != None:
         count += 1
         if hicker.marked:
            countMarked += 1
         if hicker.deletable:
            countDeletable += 1
         while hicker.prev != None:
            hicker = hicker.prev
            count += 1
            if hicker.marked:
               countMarked += 1
            if hicker.deletable:
               countDeletable += 1
         hicker = ImageHook.current
         while hicker.next != None:
            hicker = hicker.next
            count += 1
            if hicker.marked:
               countMarked += 1
            if hicker.deletable:
               countDeletable += 1
      return (count, countMarked, countDeletable, couldNotFind)

   @staticmethod
   def saveAllNotes(file):
      global couldNotFind, couldNotFindNames
      try:
         f = codecs.open(file, mode='w', encoding='utf-8')
         f.write(u'\ufeff')  # write BOM
         if ImageHook.current != None:
            if couldNotFind > 0:
               f.write(couldNotFindNames)

            print 'SAVE ALL NOTES: ' + file
            hicker = ImageHook.current.firstImage()
            # print ' ' + hicker.getFullImageInfo()    # was hicker.getCurrentImageCaption
            f.write(hicker.getFullImageInfo() + '\n')
            while hicker.next != None:
               hicker = hicker.next
               # print type(hicker.getFullImageInfo())
               # print ' ' + hicker.getFullImageInfo()
               f.write(hicker.getFullImageInfo() + '\n')
         f.close()
         # perhaps: Save LPV files with relative paths if filename entirely under LPV file's directory?  Option of course.
         return True
      except:
         return False

   def firstImage(self):
      first = self
      while first.prev != None:
         first = first.prev
      return first

   def lastImage(self):
      last = self
      while last.next != None:
         last = last.next
      return last

   def updateNotes(self, n):
      n = n.strip()
      if (len(n) + len(self.notes)) == 0 or compareText(n, self.notes, False) == 0:
         return False
      else:
         self.notes = n
         if ImageHook.sortStatus == SortStatus.sortedNotes:
            ImageHook.sortStatus = SortStatus.unsorted
         return True

   @staticmethod
   def moveToFirstImage(deletables = True):
      if ImageHook.current != None:
         ImageHook.current = ImageHook.current.firstImage()
         if not ImageHook.current.deletable or deletables:
            return ImageHook.current
         else:
            return ImageHook.moveToNextImage(deletables)  # while'ing will be done here
      else:
         return None

   @staticmethod
   def moveToLastImage(deletables = True):
      if ImageHook.current != None:
         ImageHook.current = ImageHook.current.lastImage()
         if not ImageHook.current.deletable or deletables:
            return ImageHook.current
         else:
            return ImageHook.moveToPrevImage(deletables)  # while'ing will be done here
      else:
         return None

   @staticmethod
   def moveToNewest(default = None, deletables = True):
      deletables = True; # TBD: I think we should ignore flag deletables here (risk of confusion
      if ImageHook.newest != None:
         ImageHook.current = ImageHook.newest
         ImageHook.newest = None
         if not ImageHook.current.deletable or deletables:
            return ImageHook.current
         else:
            return ImageHook.moveToNextImage(deletables)  # while'ing will be done here
      elif default != None:
         ImageHook.current = default
         return default
      else:
         return None

   @staticmethod
   def moveToRandImage(deletables = True):
      if ImageHook.current != None:
         hicker = ImageHook.current.firstImage()
         winner = None
         winScore = 0.0
         #winIx = 0      # next two temporary to check distribution
         #curIx = 1

         throw = random.random()   # 0..1
         if hicker.marked:
            throw *= 1.5
         elif hicker.deletable:
            if not deletables:
               throw = -1.1  # can't win
            else:
               throw /= 1.5
         hicker.selector += throw
         # print 'hike  ' , curIx , '  ' , hicker.selector
         if hicker.selector > winScore:
            winner = hicker
            winScore = hicker.selector
            #winIx = curIx

         while hicker.next != None:
            #curIx += 1
            hicker = hicker.next
            throw = random.random()   # 0..1
            if hicker.marked:
               throw *= 1.5
            elif hicker.deletable:
               if not deletables:
                  throw = -1.1  # can't win
               else:
                  throw /= 1.5
            hicker.selector += throw
            # print 'hike  ' , curIx , '  ' , hicker.selector
            if hicker.selector > winScore:
               winner = hicker
               winScore = hicker.selector
               #winIx = curIx

         if winner != None:
            winner.selector = 0.0  # set back for next round
            ImageHook.current = winner
            # winStar = '*'
            # if winner.marked:
            #    winStar = 'M'
            # print 'RAND ' + "                                                                      "[:winIx] + winStar + '       winScore=' , winScore , " name=" , winner.simpleFileName
         return winner
      else:
         return None

   @staticmethod
   def moveToSearch(search, homed):  # search has been trimmed
      # print 'SEARCHING for ' + search
      searchMarked = False
      searchDeletable = False
      if search.startswith('(marked)'):
         searchMarked = True
         search = "qWErtyuiopLkjhgfdsazxcvbnm"
      elif search.startswith('(deletable)'):
         searchDeletable = True
         search = "qWErtyuiopLkjhgfdsazxcvbnm"
      if ImageHook.current != None:
         if homed:
            start = ImageHook.current.firstImage()
         else:
            start = ImageHook.current.next

      search = search.lower()
      while start != None:
         if searchMarked and start.marked or searchDeletable and start.deletable or start.fullFileName.lower().find(search) >= 0 or start.notes.lower().find(search) >= 0:
            ImageHook.current = start
            return ImageHook.current
         start = start.next  # continue searching
      return None

   def moveToThisImage(self):
      ImageHook.current = self
      return ImageHook.current

   @staticmethod
   def moveToNextImage(deletables = True):
      while ImageHook.current.next != None:
         ImageHook.current = ImageHook.current.next
         if not ImageHook.current.deletable or deletables:
            return ImageHook.current
      return None

   @staticmethod
   def moveToPrevImage(deletables = True):
      while ImageHook.current.prev != None:
         ImageHook.current = ImageHook.current.prev
         if not ImageHook.current.deletable or deletables:
            return ImageHook.current
      return None

   @staticmethod
   def moveToEnd(deletables = True):
      prev = ImageHook.current.prev
      if ImageHook.current.next != None:  # otherwise nothing to do
         toMove = ImageHook.current
         end = ImageHook.current.next.lastImage()
         if toMove.prev != None:        # position current on something sane (temporarily)
            ImageHook.current = toMove.prev
         else:
            ImageHook.current = toMove.next
         if toMove.prev != None:        # unhook
            toMove.prev.next = toMove.next
         if toMove.next != None:
            toMove.next.prev = toMove.prev

         toMove.prev = end
         end.next = toMove
         toMove.next = None
      return prev

   def significantChange(self, other):
      significantChange = False
      if ImageHook.sortStatus == SortStatus.sortedNotes:       # use first word of notes
         if self.notes != u'' and other.notes == u'':
            significantChange = True
         elif self.notes == u'' and other.notes != u'':
            significantChange = True
         else:
            currentFirstWord = self.notes.split()[0].lower()
            otherFirstWord = other.notes.split()[0].lower()
            if currentFirstWord != otherFirstWord:
               significantChange = True
      elif ImageHook.sortStatus == SortStatus.sortedFullName:  # use directory
         ixs = self.fullFileName.rfind('/')  # there has to be one
         ixo = other.fullFileName.rfind('/')
         if self.fullFileName[0:ixs+1] != other.fullFileName[0:ixo+1]:
            significantChange = True
      elif ImageHook.sortStatus == SortStatus.sortedSize:      # use order of magnitude of size
         if math.floor(math.log10(self.fileSize)) != math.floor(math.log10(other.fileSize)):
            significantChange = True
      else:                                                    # use date
         if abs(self.fileDate - other.fileDate) > 7*3600:
            significantChange = True
      return significantChange

   @staticmethod
   def moveToNextDate(deletables = True):
      while ImageHook.current.next != None:
         ImageHook.current = ImageHook.current.next
         if (not ImageHook.current.deletable or deletables) and ImageHook.current.significantChange(ImageHook.current.prev):
            return ImageHook.current
      return None

   @staticmethod
   def moveToPrevDate(deletables = True):
      while ImageHook.current.prev != None:
         ImageHook.current = ImageHook.current.prev
         if (not ImageHook.current.deletable or deletables) and ImageHook.current.significantChange(ImageHook.current.next):
            return ImageHook.current
      return None

   def getCurrentImageCaption(self):
      date = datetime.fromtimestamp(self.fileDate).strftime('%Y-%m-%d %H:%M')
      if self.exifDate != None:
         eDate = "  exif: " + self.exifDate
      else:
         eDate = ""
      if self.deletable:
         return "(deletable) " + self.simpleFileName + "  [" + date + "]  size=" + str(self.width) + "x" + str(self.height) + eDate
      elif self.marked:
         return "(marked) " + self.simpleFileName + "  [" + date + "]  size=" + str(self.width) + "x" + str(self.height) + eDate
      else:
         return self.simpleFileName + "  [" + date + "]  size=" + str(self.width) + "x" + str(self.height) + eDate

   def getNotesForNotes(self):
      if len(self.notes) < 1:
         return ''
      else:
         return '\n  Notes=' + self.notes

   def getFullImageInfo(self):
      date = datetime.fromtimestamp(self.fileDate).strftime('%Y-%m-%d %H:%M')
      if self.deletable:
         return self.fullFileName + "\n  (deletable)\n  Date=" + date + "  size=" + str(self.width) + "x" + str(self.height) + self.getNotesForNotes() + "\n" + self.getMetaData()
      elif self.marked:
         return self.fullFileName + "\n  (marked)\n  Date=" + date + "  size=" + str(self.width) + "x" + str(self.height) + self.getNotesForNotes() + "\n" + self.getMetaData()
      else:
         return self.fullFileName + "\n  Date=" + date + "  size=" + str(self.width) + "x" + str(self.height) + self.getNotesForNotes() + "\n" + self.getMetaData()

   def getMetaData(self):
      return self.exifMetadata

   @staticmethod
   def getPrevOther(start):
      other = start
      while other.prev != None:
         other = other.prev
         if len(other.notes) > 1 and other.notes != start.notes:
            break
      return other

   @staticmethod
   def getNextOther(start):
      other = start
      while other.next != None:
         other = other.next
         if len(other.notes) > 1 and other.notes != start.notes:
            break
      return other

   @staticmethod
   def addImage(adding):
      if ImageHook.current == None:
         # print 'First image: ' + printable(adding.fullFileName)
         adding.next = None
         adding.prev = None
         ImageHook.current = adding
      else:
         # print 'Next image: ' + printable(adding.fullFileName)
         adding.next = ImageHook.current.next
         ImageHook.current.next = adding
         adding.prev = ImageHook.current
         ImageHook.current = adding
         if adding.next != None:
            adding.next.prev = adding
      ImageHook.sortStatus = SortStatus.unsorted

   @staticmethod
   def clearAll():
      global couldNotFind, couldNotFindNames    # darn easy bug to do?!!
      ImageHook.sortStatus = SortStatus.unsorted
      ImageHook.current = None
      ImageHook.newest = None
      couldNotFind = 0
      couldNotFindNames = u""
      lastError = None

   @staticmethod
   def lpvSortName(s, m):
      return compareText(s.sortKey[9:], m.sortKey[9:])

   @staticmethod
   def lpvSortDate(s, m):
      return compareText(s.sortKey, m.sortKey)

   @staticmethod
   def lpvSortFlags(s, m):
      return (s.deletable - s.marked) - (m.deletable - m.marked)

   @staticmethod
   def lpvSortNotes(s, m):
      return compareText(s.notes, m.notes, False)

   @staticmethod
   def lpvSortFullName(s, m):
      return compareText(s.fullFileName, m.fullFileName)

   @staticmethod
   def lpvSortSize(s, m):
      return s.fileSize - m.fileSize

   def lpvSortGeneric(self, order):
      sorter = {                                             \
            SortStatus.sortedDate:     ImageHook.lpvSortDate, \
            SortStatus.sortedName:     ImageHook.lpvSortName,  \
            SortStatus.sortedFlags:    ImageHook.lpvSortFlags,  \
            SortStatus.sortedNotes:    ImageHook.lpvSortNotes,   \
            SortStatus.sortedFullName: ImageHook.lpvSortFullName, \
            SortStatus.sortedSize:     ImageHook.lpvSortSize,      }.get(order, None)

      if sorter == None:
         return self

      sorted = self.firstImage()
      unsorted = sorted.next
      sorted.next = None
      while unsorted != None:
         moving = unsorted
         unsorted = moving.next  # ready for next loop
         sorted = sorted.firstImage()
         while sorter(sorted, moving) <= 0:
            if sorted.next != None:
               sorted = sorted.next
               continue
            else:  # insert at end
               sorted.next = moving
               moving.prev = sorted
               moving.next = None
               moving = None  # signal done
               break
         if moving != None:   # found a key that is bigger, insert before
            moving.prev = sorted.prev
            if sorted.prev != None:
               sorted.prev.next = moving
            sorted.prev = moving
            moving.next = sorted
      ImageHook.sortStatus = order
      return self


# //////////////////////////////////////////////////////////////////////////////////////////////////////////

# http://www.toptal.com/python/top-10-mistakes-that-python-programmers-make

[
   ID_SET_GREYSCALE,
   ID_SET_UPSIDE_DOWN,
   ID_SET_OVER_UNDER,
   ID_SET_DELETABLES,
   ID_SET_SLIDE_SHOW,
   ID_IMAGE_EDIT,
] = map(lambda _init_ctrls: wx.NewId(), range(6))

interestingExifTags = [ # http://www.exiv2.org/tags.html
   'Orientation',
   'DateTimeOriginal',
   'ISOSpeedRatings',
   'FocalLength',
   'FNumber',
   'ExposureTime',
   'ImageDescription',  #   ascii only?
   'UserComment',       # in Exif.Photo - unicode
]

macFilenames = 'first'

class LpvWxApp(wx.App):

   top = None

   def __init__(self, top):
      self.top = top
      wx.App.__init__(self)

   # OnInit() does not appear to bring anything

   # http://wiki.wxpython.org/Optimizing%20for%20Mac%20OS%20X
   # for following -- requires that argv emulation be disabled in py2app options

   def MacOpenFiles(self, filenames):
      global macFilenames
      if macFilenames != 'first':   # it isn't first time
         # print 'TMP MacOpenFiles - processing now'
         self.top.OnDropFiles(0, 0, filenames)
      else:
         # print 'TMP MacOpenFiles - defer until fully started'
         macFilenames = filenames

   def MacOpenFile(self, filename):       # this and next few not seen yet
      # print 'TMP MacOpenFile'
      self.top.OnDropFiles(0, 0, [filename])

   def OpenFileMessage(self, filename):
      # print 'TMP OpenFileMessage'
      self.top.OnDropFiles(0, 0, [filename])

   def MacReopenApp(self):
      # print 'TMP MacReopenApp'
      pass
                                          # seen
   def MacNewFile(self):
      # print 'TMP MacNewFile'
      pass

# Basic GUI structure
#    wx.Frame
#       wx.MenuBar
#          wx.Menu
#       wx.Panel       self.controls
#          wx.Button
#          wx.BitmapButton     <- wx.Bitmap
#          wx.Slider
#       wx.StaticText                                wx.Image
#       wx.TextCtrl                                     |
#       wx.Panel       self.panel                       V
#          wx.StaticBitmap     <- wx.BitmapFromImage(postImage)
#          (dynamic)

class LpvWxTop(wx.Frame, wx.FileDropTarget):

   # REMOVE defaultImage = 'C:/Users/pilewis/Desktop/LpvJavaFX/ccsqcart96.jpg'

   bitmap = None

   showing = None       # ImageHook
   otherImage = None    # ImageHook - used to recall notes from prev/next images
   imageShowing = None  # wx.Image

   searchString = ''

   globalGreyscale = False
   globalRotation = 0
   showDeletables = False
   showBlacksBurns = False

   logo = wx.Image(imageDir + 'lpv.png', wx.BITMAP_TYPE_ANY)
   badLogo = wx.Image(imageDir + 'lpvBroken.png', wx.BITMAP_TYPE_ANY)

   notesFile = None
   notesAdded = False
   deletesOrMarksAdded = False

   shifted = False

   def __init__(self, pps):
      global qpvVersion, chiffreEnv

      # Every wx app must create one App object
      # before it does anything else using wx.
      self.app = LpvWxApp(self) # was = wx.App()

      # Set up the main window
      wx.Frame.__init__(self,
                    parent=None,
                    title='LpvWx',
                    size=(800, 600))

      if os.name == 'posix' and sys.platform.lower() == 'darwin':
         seven = 2  # a hack to get wx.Buttons to align properly on MacOS
      else:
         seven = 7

      wx.FileDropTarget.__init__(self)
      self.SetDropTarget(self)

      menuBar = wx.MenuBar()
      # NOGO menuBar.SetSize((161,20))

      fileMenu = wx.Menu()

      fitem = fileMenu.Append(-1, 'Save Notes', 'Save notes to text file on disk.')   # was wx.ID_SAVE  (these cause funny behavior on Mac
      self.Bind(wx.EVT_MENU, self.menuSave, fitem)

      fitem = fileMenu.Append(-1, 'Save Notes As...', 'Save notes to named text file on disk.')   # was wx.ID_SAVEAS
      self.Bind(wx.EVT_MENU, self.menuSaveAs, fitem)

      fitem = fileMenu.Append(-1, 'Load...', 'Load one or more images.')   # was wx.ID_OPEN
      self.Bind(wx.EVT_MENU, self.menuLoad, fitem)

      fitem = fileMenu.Append(-1, 'Load URL...', 'Load image from URL.')
      self.Bind(wx.EVT_MENU, self.menuLoadUrl, fitem)

      fitem = fileMenu.Append(-1, 'Load Test Image', 'Load test image.')
      self.Bind(wx.EVT_MENU, self.menuLoadCalib, fitem)

      fileMenu.AppendSeparator()

      fitem = fileMenu.Append(-1, 'Clear Set', 'Clear image set.')
      self.Bind(wx.EVT_MENU, self.menuClearAll, fitem)

      fitem = fileMenu.Append(wx.ID_EXIT, 'Exit', 'Exit program.')   # is wx.ID_EXIT to please MacOS (otherwise, we get an extra one which I don't know how to catch yet
      self.Bind(wx.EVT_MENU, self.menuExit, fitem)

      menuBar.Append(fileMenu, '&File')

      self.setMenu = wx.Menu()

      fitem = self.setMenu.Append(-1, 'Sort Name', 'Sort image set based on simple name.')
      self.Bind(wx.EVT_MENU, self.menuSortName, fitem)

      fitem = self.setMenu.Append(-1, 'Sort Date', 'Sort image set based on date of file.')
      self.Bind(wx.EVT_MENU, self.menuSortDate, fitem)

      fitem = self.setMenu.Append(-1, 'Sort Flags (marks)', 'Sort image set based on marks.')
      self.Bind(wx.EVT_MENU, self.menuSortFlags, fitem)

      fitem = self.setMenu.Append(-1, 'Sort Notes', 'Sort image set based on notes.')
      self.Bind(wx.EVT_MENU, self.menuSortNotes, fitem)

      fitem = self.setMenu.Append(-1, 'Sort Full Name', 'Sort image set based on full image path.')
      self.Bind(wx.EVT_MENU, self.menuSortFullName, fitem)

      fitem = self.setMenu.Append(-1, 'Sort Size', 'Sort image set based on file size.')
      self.Bind(wx.EVT_MENU, self.menuSortSize, fitem)

      self.setMenu.AppendSeparator()

      fitem = self.setMenu.Append(ID_SET_GREYSCALE, 'Show All in Greyscale', 'Show all images in greyscale.')
      self.Bind(wx.EVT_MENU, self.menuColorGreyscale, fitem)

      fitem = self.setMenu.Append(ID_SET_UPSIDE_DOWN, 'Show All Upside Down', 'Show all images upside down.')
      self.Bind(wx.EVT_MENU, self.menuUpsideDownToggle, fitem)

      fitem = self.setMenu.Append(ID_SET_OVER_UNDER, 'Show Over/underexposure', 'Show over/under exposure.')
      self.Bind(wx.EVT_MENU, self.menuShowBlacksBurns, fitem)
      fitem.Enable(False)  # TBD some day

      self.setMenu.AppendSeparator()

      fitem = self.setMenu.Append(ID_SET_DELETABLES, 'Show Deletable Images', 'Show deletable images.')
      self.Bind(wx.EVT_MENU, self.menuShowDeletables, fitem)

      fitem = self.setMenu.Append(-1, 'Clear Flags', 'Clear all flags.')
      self.Bind(wx.EVT_MENU, self.menuClearFlags, fitem)
      fitem.Enable(False)  # TBD some day

      self.setMenu.AppendSeparator()

      fitem = self.setMenu.Append(ID_SET_SLIDE_SHOW, 'Start Slide Show', 'Start random slide show.')
      self.Bind(wx.EVT_MENU, self.menuSlideShow, fitem)

      menuBar.Append(self.setMenu, '&Set')

      imageMenu = wx.Menu()

      fitem = imageMenu.Append(-1, 'Copy Info', 'Copy basic image info to clipboard.')
      self.Bind(wx.EVT_MENU, self.menuCopyInfo, fitem)

      fitem = imageMenu.Append(-1, 'Copy Bitmap', 'Copy original image bitmap to clipboard.')   # was wx.ID_COPY
      self.Bind(wx.EVT_MENU, self.menuCopyImage, fitem)

      fitem = imageMenu.Append(-1, 'View Metadata', 'View image metadata.')
      self.Bind(wx.EVT_MENU, self.menuViewMetadata, fitem)

      imageMenu.AppendSeparator()

      fitem = imageMenu.Append(ID_IMAGE_EDIT, 'Edit', '...')   # was wx.ID_EDIT
      self.Bind(wx.EVT_MENU, self.menuEditImage, fitem)

      menuBar.Append(imageMenu, '&Image')

      helpMenu = wx.Menu()

      fitem = helpMenu.Append(-1, 'About', 'Two words about this program.')   # was wx.ID_ABOUT
      self.Bind(wx.EVT_MENU, self.menuAbout, fitem)

      fitem = helpMenu.Append(-1, 'Short Help', 'Short local help.')   # was wx.ID_HELP
      self.Bind(wx.EVT_MENU, self.menuShortHelp, fitem)

      fitem = helpMenu.Append(-1, 'Web Help', 'Web page with more details.')
      self.Bind(wx.EVT_MENU, self.menuHelp, fitem)

      menuBar.Append(helpMenu, '&Help')

      # initial settings
      if image_editor == None:
         imageMenu.Enable(ID_IMAGE_EDIT, False)

      self.SetMenuBar(menuBar)  # TODO: can I make this bar occupy only a portion of horizontal width?

      clientSize = self.GetClientSize()

      # now the rest of the UI
      self.SetAutoLayout(True)
      self.SetBackgroundColour(wx.Colour(255, 255, 255))

      self.Bind(wx.EVT_KEY_DOWN, self.key_press)  # useful on Windows
      self.Bind(wx.EVT_KEY_UP, self.key_up)

      leftWidth = wx.Button.GetDefaultSize()[0]
      stepH = wx.Button.GetDefaultSize()[1] + 3
      # print 'wx.Button width/height = ' , leftWidth, stepH

      self.controls = wx.Panel(self, size=(leftWidth+15, clientSize[1]-155), pos=(0,79), style=wx.NO_BORDER|wx.WANTS_CHARS)
      self.controls.SetBackgroundColour('WHITE')  # Linux defaults to grey
      self.controls.SetConstraints(anchors.LayoutAnchors(self.controls, True, True, False, True))  # left, top, right, bottom
      self.controls.Bind(wx.EVT_KEY_DOWN, self.key_press)
      self.controls.Bind(wx.EVT_KEY_UP, self.key_up)

      yPos = 90-79    # why -87 ? Ah yes, from wx.Panel's position

      #  size=(75,0)
      self.buttonPrev = wx.Button(self.controls, -1, '&Prev', pos=(seven,yPos))
      yPos += stepH
      self.buttonNext = wx.Button(self.controls, -1, '&Next', pos=(seven,yPos))
      yPos += stepH + 11
      self.buttonHome = wx.Button(self.controls, -1, '&Home', pos=(seven,yPos))
      yPos += stepH + 15

      Limage = wx.Bitmap(imageDir + 'ls.png', wx.BITMAP_TYPE_ANY)
      Rimage = wx.Bitmap(imageDir + 'rs.png', wx.BITMAP_TYPE_ANY)
      Fimage = wx.Bitmap(imageDir + 'fs.png', wx.BITMAP_TYPE_ANY)

      self.buttonL = wx.BitmapButton(self.controls, -1, bitmap=Limage, pos=(7, yPos))
      rotatorWidth = self.buttonL.GetSize()[0]
      # print 'wx.ButtonR width = ' + str(rotatorWidth)
      center = 1 + (7 + (7 + leftWidth)) / 2
      self.buttonL.SetPosition((center - rotatorWidth/2 - 2 - rotatorWidth, yPos))           # was 7, 32, 57
      self.buttonR = wx.BitmapButton(self.controls, -1, bitmap=Rimage, pos=(center - rotatorWidth/2, yPos))
      self.buttonF = wx.BitmapButton(self.controls, -1, bitmap=Fimage, pos=(center + rotatorWidth/2 + 2, yPos))
      yPos += stepH + 11
      self.buttonGrey = wx.Button(self.controls, -1, '&Grey/color', pos=(seven,yPos))
      yPos += stepH
      self.gammaSlider = wx.Slider(self.controls, -1, 100, 50, 150, pos=(7, yPos), size=(leftWidth, 27))
      yPos += stepH
      self.gammaReset = wx.Button(self.controls, -1, 'Reset', pos=(seven,yPos))
      yPos += stepH + 15
      self.buttonToEnd = wx.Button(self.controls, -1, 'To end', pos=(seven,yPos))
      yPos += stepH + 15
      self.buttonMark = wx.Button(self.controls, -1, '&Mark', pos=(seven,yPos))
      yPos += stepH
      self.buttonDelete = wx.Button(self.controls, -1, '&Deletable', pos=(seven,yPos))
      yPos += stepH + 10

      self.buttonNext.Bind(wx.EVT_BUTTON, self.next_button)
      self.buttonPrev.Bind(wx.EVT_BUTTON, self.prev_button)
      self.buttonHome.Bind(wx.EVT_BUTTON, self.home_button)

      self.buttonL.Bind(wx.EVT_BUTTON, self.rotate_button)
      self.buttonR.Bind(wx.EVT_BUTTON, self.rotate_button)
      self.buttonF.Bind(wx.EVT_BUTTON, self.rotate_button)

      self.buttonGrey.Bind(wx.EVT_BUTTON, self.grey_color_button)

      self.gammaSlider.Bind(wx.EVT_SLIDER, self.slider_move)
      self.gammaReset.Bind(wx.EVT_BUTTON, self.slider_reset)

      self.buttonToEnd.Bind(wx.EVT_BUTTON, self.move_to_end_button)

      self.buttonDelete.Bind(wx.EVT_BUTTON, self.delete_button)
      self.buttonMark.Bind(wx.EVT_BUTTON, self.mark_button)

      self.controls.Bind(wx.EVT_LEFT_DOWN, self.focus_panel)   # left mouse button

      self.imageLabel = wx.StaticText(self, -1, 'Image:', pos=(7,clientSize[1]-51))
      self.imageLabel.SetConstraints(anchors.LayoutAnchors(self.imageLabel, True, False, False, True)) # left, top, right, bottom
      self.notesLabel = wx.StaticText(self, -1, 'Notes:', pos=(7,clientSize[1]-31))
      self.notesLabel.SetConstraints(anchors.LayoutAnchors(self.notesLabel, True, False, False, True))

      textWidth , textHeight = self.imageLabel.GetSize()
      # print 'wx.StaticText width = ' + str(textWidth)

      self.lpvMessage = wx.StaticText(self, -1, "Lew's Picture Viewer, version " + str(qpvVersion) + ", based on wxPython.", pos=(7,1), size=(800-7-7,textHeight)) # pos=(160 if besides menu bar)

      self.noteTaker = wx.TextCtrl(self, -1, 'Input area...', pos=(textWidth+9,clientSize[1]-28), size=(clientSize[0]-19-textWidth, -1), style=wx.TE_PROCESS_ENTER)  # may need to force single-line
      self.noteTaker.SetConstraints(anchors.LayoutAnchors(self.noteTaker, True, False, True, True))
      self.noteTaker.Bind(wx.EVT_TEXT_ENTER, self.notes_entered)
      self.noteTaker.Bind(wx.EVT_KEY_DOWN, self.key_press_notes)  # will it work?
      self.noteTaker.Bind(wx.EVT_KEY_UP, self.key_up)
      self.fileSummary = wx.StaticText(self, -1, '(file summary)', pos=(textWidth+13,clientSize[1]-51), size=(clientSize[0]-textWidth-13-7,textHeight))  # without size, we see truncation in some contexts
      self.fileSummary.SetConstraints(anchors.LayoutAnchors(self.fileSummary, True, False, True, True))

      self.panel = wx.Panel(self, size=(clientSize[0]-leftWidth-7-15, clientSize[1]-77), pos=(leftWidth+15,21), style=wx.NO_BORDER|wx.WANTS_CHARS)
      self.panel.SetConstraints(anchors.LayoutAnchors(self.panel, True, True, True, True))
      self.panel.SetBackgroundColour('WHITE')  # needed for Linux
      #self.panel.SetBackgroundColour(wx.Colour(240, 240, 240))  # TEMPORARY
      self.panel.Bind(wx.EVT_SIZE, self.resize_panel)
      # print 'self.panel.AcceptsFocus(): ' + str(self.panel.AcceptsFocus())
      self.panel.Bind(wx.EVT_KEY_DOWN, self.key_press)
      self.panel.Bind(wx.EVT_KEY_UP, self.key_up)
      self.panel.Bind(wx.EVT_LEFT_DOWN, self.imageMouseDown)
      self.bitmap = wx.StaticBitmap(self.panel, -1, wx.BitmapFromImage(self.logo))
      self.bitmap.Bind(wx.EVT_LEFT_DOWN, self.imageMouseDown)

      greenCheckImage = wx.Image(imageDir + 'greenCheck.png', wx.BITMAP_TYPE_ANY)
      redCrossImage = wx.Image(imageDir + 'redCross.png', wx.BITMAP_TYPE_ANY)
      loupeImage = wx.Image(imageDir + 'loupe.png', wx.BITMAP_TYPE_ANY)
      self.greenCheck = wx.StaticBitmap(self, -1, wx.BitmapFromImage(greenCheckImage), (33, 31))
      self.redCross = wx.StaticBitmap(self, -1, wx.BitmapFromImage(redCrossImage), (27, 21))
      self.loupe = wx.StaticBitmap(self.controls, -1, wx.BitmapFromImage(loupeImage), (13, yPos))
      self.greenCheck.Hide()
      self.redCross.Hide()
      self.loupe.Hide()

      self.timer = None

      self.chiffreOrig = chiffreEnv

      self.Bind(wx.EVT_CLOSE, self.on_close)

      toBeShown = None     # ImageHook

      added  = 0
      for p in pps:
         # print 'PROCESSING ' + printable(p)
         added += processParameter(p)
         # print 'ADDED ' + str(added)
         if len(pps) == 1:  # single parm, get whole dir # perhaps skip if command-line? Ie. not d-click
            if p.lower().endswith('.lpv'):       # IFs re-ordered to avoid loading all images of directory if lpv contains just one name
               self.notesFile = p
            elif added == 1:  # single image, get whole dir
               global couldNotFind, couldNotFindNames
               firstImageToShow = ImageHook.current.fullFileName

               ImageHook.current = None
               ImageHook.sortStatus = SortStatus.unsorted
               couldNotFind = 0
               couldNotFindNames = u""
               lastError = None
               added = 0

               extIx = firstImageToShow.rfind('/')  # there has to be one
               p = firstImageToShow[0:extIx+1]
               added += processParameter(p)
               toBeShown = ImageHook.findImage(firstImageToShow)

      ImageHook.newest = None

      if toBeShown != None:
         self.showing = toBeShown.moveToThisImage()
      else:
         self.showing = ImageHook.moveToFirstImage(self.showDeletables)
      self.otherImage = self.showing

      self.lpvMessage.SetLabel("Images added to image set: " + str(added) + ".")
      print "STARTING with " + str(added) + " images"

      self.show()

      self.panel.SetFocus()

      # set up DnD
      # self.fdt = wx.FileDropTarget()

   def checkNotes(self):
      notes = self.noteTaker.GetValue().strip()
      if self.showing != None:
         if len(notes) > 0 and self.showing != None and self.showing.notes != notes:    # was: self.noteTaker.IsModified():
            # print 'NOTES modified: ' + notes              + str(len(notes))
            # print '           was: ' + self.showing.notes + str(len(self.showing.notes))
            self.showing.notes = notes
            self.notesAdded = True;
            self.noteTaker.SetModified(False)
         #else:
         #   print 'NOTES not modified: ' + printable(notes)      # TBD sometimes buggy on iMac because not ASCII?


   def OnDropFiles(self, x, y, names):
      hook = self.showing
      added = 0
      if self.showing == None:
         hook = ImageHook.moveToLastImage(True)
      # print 'Files dropped'
      for p in names:
         # print 'PROCESSING ' + printable(p) + " (type: " + str(type(p))
         added += processParameter(p)
         # print 'ADDED ' + str(added)
      if added > 0:
         self.showing = ImageHook.moveToNewest(hook, self.showDeletables)
         self.otherImage = self.showing
         self.show()
         if self.IsIconized():
            self.Iconize(False)

   def show(self):
      global pythDir

      if self.showing != None:

         self.otherImage = self.showing
         name = self.showing.fullFileName
         rotation = self.showing.rotation

         self.redCross.Show(self.showing.deletable)
         self.greenCheck.Show(self.showing.marked)

         self.gammaSlider.SetValue(self.showing.gamma)

         # print ' '
         # print 'TMP: SHOWING: ' + printable(name)
         self.lpvMessage.SetLabel('Showing ' + name)

         ll = wx.Log.GetLogLevel()
         wx.Log.SetLogLevel(0)  # to avoid warnings such as iCCP: known incorrect sRGB profile

         if name.startswith('http://') or name.startswith('https://'):
            try:
               f = urllib.urlopen(name)       # proxies need extra parms
               bytes = f.read()
               f.close()
               self.imageShowing = wx.ImageFromStream(StringIO(bytes))
               if self.imageShowing.GetWidth() < 1:       # test that we got a valid image
                  raise IOError('Not an image')
               self.showing.width = self.imageShowing.GetWidth() # test sanity and update info
               self.showing.height = self.imageShowing.GetHeight()
            except:
               # print 'NO GO '
               self.imageShowing = self.badLogo

         else:
            try:
               if self.showing.sonderbar:
                  raise IOError('Wir wissen, dass es chiffriert ist')

               # the usual case
               self.imageShowing = wx.Image(name, wx.BITMAP_TYPE_ANY)

               self.showing.width = self.imageShowing.GetWidth() # test sanity and update info
               self.showing.height = self.imageShowing.GetHeight()

               exifString = ''

               if rotation == 360:  # first time

                  rotation = 0  # default

                  # http://www.blog.pythonlibrary.org/2010/04/10/adding-an-exif-viewer-to-the-image-viewer/
                  if hasPIL:
                     try:
                        exif_data = {}
                        exif = Image.open(name)
                        # print 'Image.info: ', exif.format, exif.size, exif.mode
                        try:
                           dpi = exif.info['dpi']
                           # print '  DPI ', dpi
                        except:
                           # print '  No DPI info'
                           pass

                        info = exif._getexif()
                        # print "EXIF:"
                        if info != None and len(info.items()) > 0:
                           exifNotesID = u''
                           exifNotesUC = u''
                           for tag, value in info.items():
                              decoded = TAGS.get(tag, tag)
                              exif_data[decoded] = value
                              if len(str(value)) < 25:
                                 if str(decoded) in interestingExifTags:
                                     if str(decoded) == 'ResolutionUnit':
                                         pass
                                         # if value != 2: # omit usual inches
                                         #     print '   ' + str(decoded) + ': ' + ['zero', 'none', 'inches', 'cm'][value]
                                     elif str(decoded) == 'DateTimeOriginal':
                                         # print '   ' + str(decoded) + ': ' + str(value)
                                         self.showing.exifDate = str(value)
                                     else:
                                         pass
                                         # print '   ' + str(decoded) + ': ' + str(value)
                                     exifString += '  ' + str(decoded) + ': ' + str(value) + '\n'

                              if str(decoded) == 'Orientation':  # see dict approach below
                                 if value == 3 or value == 4:
                                    rotation = 180
                                 elif value == 5 or value == 6:
                                    rotation = 90
                                 elif value == 7 or value == 8:
                                    rotation = 270
                              if self.showing.notes == u'':
                                 if str(decoded) == 'ImageDescription':
                                    lgt = len(value)
                                    for k in xrange(lgt):
                                       if value[k] < ' ':
                                          lgt = k
                                          value = value[:lgt]
                                          break
                                    if len(value) > 0:
                                       exifNotesID = local2uni(value).strip()
                                 elif str(decoded) == 'UserComment':
                                    lgt = len(value)
                                    # handle in-band type, strip trailing NULs  (see comments below)
                                    if value.startswith('UNICODE\0'):
                                       while lgt > 0:
                                          if value[lgt-2:lgt-1] == '\0\0':
                                             lgt -= 2;
                                          else:
                                             break;
                                       value = unicode2uni(value[8:lgt])
                                    elif value.startswith('ASCII\0\0\0'):
                                       while lgt > 0:
                                          if value[lgt-1] == '\0':
                                             lgt -= 1;
                                          else:
                                             break;
                                       value = local2uni(value[8:lgt])
                                    # elif value.startswith('UTF-8\0\0\0'):     # LEWism
                                    #    while lgt > 0:
                                    #       if value[lgt-1] == '\0':
                                    #          lgt -= 1;
                                    #       else:
                                    #          break;
                                    #    value = utf2uni(value[8:lgt])
                                    else:  # JIS or undefined -- treat as local (and still swallow first 8 bytes?)
                                       while lgt > 0:
                                          if value[lgt-1] == '\0':
                                             lgt -= 1;
                                          else:
                                             break;
                                       value = local2uni(value[8:lgt])
                                    # keep only up to first C0 character
                                    lgt = len(value)
                                    for k in xrange(lgt):
                                       if value[k] < ' ':
                                          lgt = k
                                          value = value[:lgt]
                                          break
                                    if len(value) > 0:
                                       exifNotesUC = local2uni(value).strip()
                     except (AttributeError, IOError):
                        # print 'AttributeError or IOError getting EXIF data'
                        pass
                     except:
                        # print 'Unknown error getting EXIF data'
                        pass
                     finally:
                        if exifNotesID != u'' and exifNotesUC != u'':
                           self.showing.notes = exifNotesID + ' -- ' + exifNotesUC
                        elif exifNotesID != u'' or exifNotesUC != u'':
                           self.showing.notes = exifNotesID + exifNotesUC  # one is empty
                        pass

                  else:  # no PIL, just get the rotation
                     try:
                        fh = open(name, 'rb')
                        hdr = bytearray(min(8192,os.path.getsize(name)))  # and maybe smaller
                        lgt = fh.readinto(hdr)
                        fh.close()
                        ix = 0
                        orientation = 0
                        if hdr[0] == 0xff and hdr[1] == 0xd8:
                           ix = 2
                           while ix < lgt-14:
                              if checkHeader(hdr, ix, exifTiffIntel):
                                 # print 'TIFF header found, Intel worng-endian, ix=', ix
                                 orientation = readOrientation(hdr, ix+len(exifTiffIntel), False)
                                 break
                              elif checkHeader(hdr, ix, exifTiffMoto):
                                 # print 'TIFF header found, Moto right-endian, ix=', ix
                                 orientation = readOrientation(hdr, ix+len(exifTiffIntel), True)
                                 break
                              elif hdr[ix] == 0xff:
                                 skip = 2 + readShort(hdr, ix+2, True)
                                 ix += skip
                                 # print 'skip=', skip, 'ix=', ix
                              else:
                                 # print 'cannot grok structure, bailing out'
                                 break
                        rotation = { 3: 180, 4: 180, 5: 90, 6: 90, 7: 270, 8: 270 }.get(orientation, 0)  # alternative to case statement
                     except (IOError):
                        # print 'IOError getting rotation'
                        pass
                     except:
                        # print 'Unknown error getting rotation'
                        pass

                  self.showing.rotation = rotation  # no need to read EXIF again
                  if len(exifString) > 1:
                     self.showing.exifMetadata = exifString

            except:
               self.showing.rotation = 0
               if hasChiffre:
                  # print 'NO GO, trying chiffre '
                  try:
                     global chiffreEnv

                     fh = open(name, 'rb')
                     bytes = bytearray(os.path.getsize(name))
                     fh.readinto(bytes)
                     fh.close()

                     if chiffreEnv == '?':
                        dlg = wx.TextEntryDialog(self, 'Chiffre eingeben','LpvWx')  # includes wx.TE_PASSWORD, or use wx.TextEntryDialog -- wx.PasswordEntryDialog() does not deal correctly with latin-1 chars on MacOS!!!
                        dlg.SetValue("xxxxxxxxxxx")
                        # dlg.SetMaxLength(21)
                        if dlg.ShowModal() == wx.ID_OK:   # https://docs.python.org/2/howto/unicode.html
                           chiffreEnvNew = dlg.GetValue()  # unicode it seems
                           chiffreEnvNew = chiffreEnvNew.encode('iso-8859-1')  # returns type str
                           # print 'Dialog type=' + str(type(chiffreEnvNew))
                           if chiffreEnvNew != "xxxxxxxxxxx":
                              chiffreEnv = chiffreEnvNew
                              # print 'CHIFFRE ' + chiffreEnv + ' len=' + str(len(chiffreEnv))
                        dlg.Destroy()

                     if cchiffre.cchiffre(bytes, chiffreEnv):
                        self.imageShowing = wx.ImageFromStream(StringIO(bytes[8:]))
                        self.showing.width = self.imageShowing.GetWidth() # test sanity and update info
                        self.showing.height = self.imageShowing.GetHeight()
                        self.showing.sonderbar = True
                        # print '   (chiffriert) '
                        #NOGO: self.imageShowing = wx.Image(StringIO(bytes), wx.BITMAP_TYPE_ANY)
                     else:
                        # print 'NO GO chiffre complains '
                        self.imageShowing = self.badLogo

                  except:
                     # print 'NO GO again '
                     self.imageShowing = self.badLogo
               else:
                  # print 'NO GO '
                  self.imageShowing = self.badLogo

         self.noteTaker.SetValue(self.showing.notes)
         self.noteTaker.SetInsertionPointEnd()
         self.fileSummary.SetLabel(self.showing.getCurrentImageCaption())  # at end to get image size

         wx.Log.SetLogLevel(ll)  # back to normal -- perhaps do once and for all at program start?

      else:
         # print ' '
         # print 'SHOWING: wrap point'

         self.redCross.Show(False)
         self.greenCheck.Show(False)

         self.noteTaker.SetValue('')
         counts = ImageHook.countImages()
         if ImageHook.current != None:
            self.fileSummary.SetLabel('(wrap point / search)')
            self.lpvMessage.SetLabel("Wrap point on " + str(counts[0]) + " images (" + str(counts[1]) + " marked, " + str(counts[2]) + " deletable), " + str(counts[3]) + " missing. Next/prev to go to first/last image.")
         else:
            self.fileSummary.SetLabel('(no image)')
            self.lpvMessage.SetLabel("No image in set, " + str(counts[3]) + " missing.")

         self.imageShowing = self.logo
         self.otherImage = None

      self.postShow()

   def postShow(self, reGamma=False):

      # http://wxpython.org/Phoenix/docs/html/Image.html
      if self.showing != None:
         rotation = (self.globalRotation + self.showing.rotation) % 360
         if rotation == 90:
            # print "ROTATING 90"
            postImage = self.imageShowing.Rotate90(True)
         elif rotation == 180:
            # print "ROTATING 180"
            postImage = self.imageShowing.Rotate180()
         elif rotation == 270:
            # print "ROTATING 270"
            postImage = self.imageShowing.Rotate90(False)
         else:
            postImage = self.imageShowing

         if self.globalGreyscale or self.showing.greyscale:
            postImage = postImage.ConvertToGreyscale()

         # postImage = postImage.Mirror() # if ever I get fancier with orientations
         if reGamma or self.showing.gamma != 100:
            gamma = self.showing.gamma / 100.
            postImage = postImage.AdjustChannels(gamma, gamma, gamma)
      else:
         postImage = self.imageShowing     # a logo

      width = postImage.GetWidth()
      height = postImage.GetHeight()
      pWidth = self.panel.GetSize()[0]
      pHeight = self.panel.GetSize()[1]
      # print "SIZE=" + str(width) + 'x' + str(height) + ', PANEL=' + str(pWidth) + 'x' + str(pHeight)

      if width <= pWidth and height <= pHeight:
         # crop not needed, ignore click setting
         # was self.bitmap = wx.StaticBitmap(self.panel, -1, wx.BitmapFromImage(postImage))  # pos=((pWidth-width)/2,(pHeight-height)/2))
         self.bitmap.SetBitmap(wx.BitmapFromImage(postImage))
         self.loupe.Show(False)

      else:
         # crop is needed if click set
         if self.showing != None and self.showing.click[0] != -1.0: # crop (fun/tricky code)
            click = self.showing.click
            if self.globalRotation != 0:
               click = (1.0 - click[0], 1.0 - click[1])
            # TBD: should I not do it for all, or in postShow()?!! Same issue in C# version
            xOrigin = 0
            yOrigin = 0
            if width > pWidth:
               xOrigin = (width - pWidth) / 2
               width = pWidth
            if height > pHeight:
               yOrigin = (height - pHeight) / 2
               height = pHeight
            xOrigin += int((click[0] - 0.5) * postImage.GetWidth() + 0.5)
            yOrigin += int((click[1] - 0.5) * postImage.GetHeight() + 0.5)
            if xOrigin < 0:
               xOrigin = 0
            if yOrigin < 0:
               yOrigin = 0
            if width + xOrigin > postImage.GetWidth():
               xOrigin = postImage.GetWidth() - width
            if height + yOrigin > postImage.GetHeight():
               yOrigin = postImage.GetHeight() - height
            smallerImage = postImage.GetSubImage((xOrigin, yOrigin, width, height))
            # TBD: add visible indication of cropped
            self.loupe.Show(True)

         else: # scale down
            sWidth =  1.0 * pWidth / width
            sHeight = 1.0 * pHeight / height
            if sWidth < sHeight:
               scale = sWidth
            else:
               scale = sHeight
            # print "SCALING by " + str(scale)
            smallerImage = postImage.Scale(width * scale, height * scale, wx.IMAGE_QUALITY_HIGH)
            self.loupe.Show(False)

         # was self.bitmap = wx.StaticBitmap(self.panel, -1, wx.BitmapFromImage(smallerImage))  # pos=((pWidth-width)/2,(pHeight-height)/2))
         self.bitmap.SetBitmap(wx.BitmapFromImage(smallerImage))

      self.bitmap.CenterOnParent()

      self.panel.SetFocus()   # TBD do I want this?  Not if focus is in noteTaker

   # button handlers

   def next_button(self, e):
      self.checkNotes()
      if self.showing != None:
         if self.shifted:
            self.showing = ImageHook.moveToNextDate(self.showDeletables)
            if not ImageHook.sortStatus in usefulSorts:
               self.lpvMessage.SetLabel('Warning: image set appears unsorted, results may be surprising.')
               # print 'UNSORTED'
         else:
            self.showing = ImageHook.moveToNextImage(self.showDeletables)
      else:
         self.showing = ImageHook.moveToFirstImage(self.showDeletables)
      if self.showing == None:
         self.home_button(e)
      else:
         self.show()

   def prev_button(self, e):
      self.checkNotes()
      if self.showing != None:
         if self.shifted:
            self.showing = ImageHook.moveToPrevDate(self.showDeletables)
            if not ImageHook.sortStatus in usefulSorts:
               self.lpvMessage.SetLabel('Warning: image set appears unsorted, results may be surprising.')
               # print 'UNSORTED'
         else:
            self.showing = ImageHook.moveToPrevImage(self.showDeletables)
      else:
         self.showing = ImageHook.moveToLastImage(self.showDeletables)
      if self.showing == None:
         self.home_button(e)
      else:
         self.show()

   def home_button(self, e):
      #if e is None:             # always stop, better I think
      self.menuSlideShow(None)

      self.checkNotes()
      self.showing = None

      self.show()

   def delete_button(self, e):
      self.checkNotes()
      if self.showing != None:
         if not self.showing.marked:
            self.deletesOrMarksAdded = True
            self.showing.deletable = not self.showing.deletable
            self.redCross.Show(self.showing.deletable)
         else:
            self.lpvMessage.SetLabel('Cannot have both marks together.')
      self.panel.SetFocus()   # TBD do I want this?

   def move_to_end_button(self, e):
      self.checkNotes()
      if self.showing != None:
         self.showing = ImageHook.moveToEnd(self.showDeletables)  # returns the previous one
         if self.showing == None:
            self.showing = ImageHook.moveToFirstImage(self.showDeletables)
         else:
            self.showing.moveToThisImage()
            if self.shifted:
               self.showing = ImageHook.moveToNextDate(self.showDeletables)
               if not ImageHook.sortStatus in usefulSorts:
                  self.lpvMessage.SetLabel('Warning: image set appears unsorted, results may be surprising.')
                  # print 'UNSORTED'
            else:
               self.showing = ImageHook.moveToNextImage(self.showDeletables)
         self.show()

   def mark_button(self, e):
      self.checkNotes()
      if self.showing != None:
         if not self.showing.deletable:
            self.deletesOrMarksAdded = True
            self.showing.marked = not self.showing.marked
            self.greenCheck.Show(self.showing.marked)
         else:
            self.lpvMessage.SetLabel('Cannot have both marks together.')
      self.panel.SetFocus()   # TBD do I want this?

   def rotate_button(self, e):
      # print 'ROTATE ' , dir(e)  <=== great debugging idea
      source = e.GetEventObject()

      if self.showing != None:
         if source is self.buttonL:
            self.showing.rotation += 270
         elif source is self.buttonR:
            self.showing.rotation += 90
         elif source is self.buttonF:
            self.showing.rotation += 180
         while self.showing.rotation >= 360:
            self.showing.rotation -= 360
         self.postShow()

   def grey_color_button(self, e):
      if self.showing != None:
         self.showing.greyscale = not self.showing.greyscale
         self.postShow()

   def slider_move(self, e):
      if self.showing != None:
         gamma = self.gammaSlider.GetValue()
         if abs(self.showing.gamma - gamma) >= 5:
            self.showing.gamma = self.gammaSlider.GetValue()
            self.postShow(True)
         # print 'slider_move ' , self.gammaSlider.GetValue()

   def slider_reset(self, e):
      if self.showing != None:
         self.gammaSlider.SetValue(100)
         self.showing.gamma = 100
         self.postShow(True)
         # print 'slider_reset ', self.gammaSlider.GetValue()

   # other events

   def imageMouseDown(self, e):
      if self.showing != None:
         source = e.GetEventObject()
         if self.showing.click[0] == -1.0:
            size = self.bitmap.GetSize()
            x = e.x   # or e.GetX() &c
            y = e.y
            if source is self.panel:
               pos = self.bitmap.GetPosition()
               x -= pos[0]
               y -= pos[1]
            click = (1.0 * x / size[0], 1.0 * y / size[1])
            if 0.0 < click[0] < 1.0 and 0.0 < click[1] < 1.0:
               if self.globalRotation != 0:
                  click = (1.0 - click[0], 1.0 - click[1])  # TBD: implement this new behavior in C# version too
               self.showing.click = click
            else:
               # print 'Ignoring click, outside ' , click
               return
         else:
            self.showing.click = (-1.0, -1.0)
         self.postShow()   # called for nothing if click in small image that isn't scaled

   def focus_panel(self, e):
      self.panel.SetFocus()

   def onTimedEvent(self, e):
      self.checkNotes()
      self.showing = ImageHook.moveToRandImage(self.showDeletables)

      if self.showing == None or self.IsIconized():     # stop if no image to display or iconized (aka minimized)
         if hasChiffre:
            global chiffreEnv
            chiffreEnv = self.chiffreOrig
            self.home_button(None)
         else:
            self.menuSlideShow(None)
            self.show()
      else:
         self.show()

   def key_up(self, e):
      if self.shifted != e.ShiftDown():
         self.shifted = e.ShiftDown()
         # print 'SHIFT ' , self.shifted

   def key_press(self, e):    # http://www.wxpython.org/docs/api/wx.KeyEvent-class.html
      # c = e.GetUniChar()
      # u = e.GetUnicodeKey()
      if self.shifted != e.ShiftDown():
         self.shifted = e.ShiftDown()
         # print 'SHIFT ' , self.shifted
      k = e.GetKeyCode()
      # print 'c=' + str(c) +' u=' + str(u) + ' k=' + str(k)
      # print 'KEY PRESS k=' + str(k)
      if k == wx.WXK_RIGHT or k == wx.WXK_DOWN or k == wx.WXK_NEXT:
         self.next_button(None)
      elif k == wx.WXK_LEFT or k == wx.WXK_UP or k == wx.WXK_PRIOR:
         self.prev_button(None)
      elif k == wx.WXK_END:
         global chiffreEnv
         chiffreEnv = self.chiffreOrig
         self.home_button(None)
         self.Iconize()
      elif k == wx.WXK_HOME:
         self.home_button(None)
      elif k == wx.WXK_F3 or k == wx.WXK_TAB:   # TBD tab is for Mac where F3 does not work
         self.checkNotes()      # TBD: need this! Unless I catch noteTaker's loss of focus
         if len(self.searchString) > 1:
            self.showing = ImageHook.moveToSearch(self.searchString, self.showing == None)
            self.show()
      # else:
      #    print 'KEY PRESS k=' + str(k)


   def key_press_notes(self, e):
      if self.shifted != e.ShiftDown():
         self.shifted = e.ShiftDown()
         # print 'SHIFT ' , self.shifted
      k = e.GetKeyCode()
      # print 'KEY PRESS NOTES: k=' + str(k)
      if k == wx.WXK_UP:
         if self.showing != None and (self.showing != self.otherImage or len(self.noteTaker.GetValue()) == 0):
            self.showing.notes = u''
            newOtherImage = ImageHook.getPrevOther(self.otherImage)
            if newOtherImage != self.otherImage:
               self.noteTaker.SetValue(newOtherImage.notes)
               self.noteTaker.SetInsertionPointEnd()
               self.otherImage = newOtherImage
            else:
               self.lpvMessage.SetLabel('No more notes available (beginning of set).')
               self.noteTaker.SetValue('')
         # self.noteTaker.SetFocus()

      elif k == wx.WXK_DOWN:
         if self.showing != None and (self.showing != self.otherImage or len(self.noteTaker.GetValue()) == 0):
            self.showing.notes = u''
            newOtherImage = ImageHook.getNextOther(self.otherImage)
            if newOtherImage != self.otherImage:
               self.noteTaker.SetValue(newOtherImage.notes)
               self.noteTaker.SetInsertionPointEnd()
               self.otherImage = newOtherImage
            else:
               self.lpvMessage.SetLabel('No more notes available (end of set).')
               self.noteTaker.SetValue('')
         # self.noteTaker.SetFocus()

      elif k == wx.WXK_NEXT:
         self.next_button(None)
         self.noteTaker.SetFocus()
      elif k == wx.WXK_PRIOR:
         self.prev_button(None)
         self.noteTaker.SetFocus()
      elif k == wx.WXK_TAB:
         if self.shifted:
            self.prev_button(None)
         else:
            self.next_button(None)
         self.noteTaker.SetFocus()
      elif k == wx.WXK_END:
         global chiffreEnv
         chiffreEnv = self.chiffreOrig
         self.home_button(None)
         self.Iconize()
      elif k == wx.WXK_HOME:
         self.home_button(None)
         self.noteTaker.SetFocus()

      else:
         e.Skip()  # pass on to standard wx.TextCtrl handler

   def resize_panel(self, e):
      # print 'resize_panel: ' + str(e)
      # print 'RESIZE panel, size=' + str(self.panel.GetSize())
      # print 'RESIZE panel, size=' + str(self.panel.GetSize()[0]) + 'x' + str(self.panel.GetSize()[1])
      self.postShow()

      size = self.panel.GetSize()
      ratio = ''      # boff code
      if self.panel.GetSize()[0] >= self.panel.GetSize()[1]:    # landscape
         longer = self.panel.GetSize()[0]
         shorter = self.panel.GetSize()[1]
         if abs(shorter - longer) <= 1.0:
            ratio = '  (ratio: ~square)'
         elif abs(shorter - longer*2.0/3.0) <= 1.0:
            ratio = '  (ratio: ~3:2)'
         elif abs(shorter - longer*3.0/4.0) <= 1.0:
            ratio = '  (ratio: ~4:3)'
         elif abs(shorter - longer*5.0/8.0) <= 1.0:
            ratio = '  (ratio: ~8:5)'
         elif abs(shorter - longer*9.0/16.0) <= 1.0:
            ratio = '  (ratio: ~16:9)'
      else:                                                     # portrait
         longer = self.panel.GetSize()[1]
         shorter = self.panel.GetSize()[0]
         if abs(shorter - longer) <= 1.0:
            ratio = '  (ratio: ~square)'
         elif abs(shorter - longer*2.0/3.0) <= 1.0:
            ratio = '  (ratio: ~2:3)'
         elif abs(shorter - longer*3.0/4.0) <= 1.0:
            ratio = '  (ratio: ~3:4)'
         elif abs(shorter - longer*5.0/8.0) <= 1.0:
            ratio = '  (ratio: ~5:8)'
         elif abs(shorter - longer*9.0/16.0) <= 1.0:
            ratio = '  (ratio: ~9:16)'

      self.lpvMessage.SetLabel('Panel resized to ' + str(self.panel.GetSize()) + ratio)

   def notes_entered(self, e):
      # print 'NOTES ENTERED'
      if self.showing == None:  # search
         self.searchString = self.noteTaker.GetValue().strip()
         if len(self.searchString) > 1:
            self.showing = ImageHook.moveToSearch(self.searchString, True)
            self.show()
      else:
         self.checkNotes()
         self.panel.SetFocus()   # TBD do I want this?

   # menu handlers

   def menuSave(self, e):
      self.checkNotes()
      if self.notesFile != None:
         done = ImageHook.saveAllNotes(self.notesFile)
         if done:
            self.lpvMessage.SetLabel("Notes saved to " + self.notesFile + " .")
            self.notesAdded = False
            self.deletesOrMarksAdded = False
         else:
            self.lpvMessage.SetLabel("Problem saving notes to " + self.notesFile + " .")
      else:
         self.menuSaveAs(e)

   def menuSaveAs(self, e):
      dlg = wx.FileDialog(self, "Save notes as *.lpv file",  "", "", "LPV files (*.lpv)|*.lpv", wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
      if dlg.ShowModal() != wx.ID_CANCEL:
         target = dlg.GetPath()
         # above dialog already checks that file exists or not, so following not needed, just keeping as example
         # if os.path.exists(target):
         #    dlg2 = wx.MessageDialog(self, message='This file already exists, do you want to overwrite it?', caption='caption', style=wx.OK|wx.CANCEL)
         #    if dlg2.ShowModal() != wx.OK:
         #       return
         self.notesFile = target
         self.menuSave(e)

   def menuLoad(self, e):       # http://wxpython.org/Phoenix/docs/html/FileDialog.html
      self.checkNotes()
      hook = self.showing
      added = 0
      dlg = wx.FileDialog(self, "Open picture/text file(s)", "", "", "*", wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE)
      if dlg.ShowModal() != wx.ID_CANCEL:
         files = dlg.GetPaths()
         # print 'File to open (' + str(type(files[0])) + '): ' + str(files)
         for p in files:
            # print 'PROCESSING ' + printable(p) + " (type: " + str(type(p))
            added += processParameter(p)
            # print 'ADDED ' + str(added)
         if added > 0:
            self.showing = ImageHook.moveToNewest(hook, self.showDeletables)
            self.otherImage = self.showing
            self.show()

   def menuLoadUrl(self, e):     # no automatic proxy stuff here as with C#/WPF
      self.checkNotes()
      hook = self.showing
      added = 0
      dlg = wx.TextEntryDialog(self, 'Enter URL','LpvWx')
      dlg.SetValue("http://")
      # TBD: could load picture of author from web :-)
      if dlg.ShowModal() != wx.ID_CANCEL:
         url = dlg.GetValue()  # unicode ?
         # print 'URL to open (' + str(type(url)) + '): ' + str(url)
         # print 'PROCESSING ' + url + " (type: " + str(type(url))
         added += processParameter(url)
         # print 'ADDED ' + str(added)
         if added > 0:
            self.showing = ImageHook.moveToNewest(hook, self.showDeletables)
            self.otherImage = self.showing
            self.show()

   def menuLoadCalib(self, e):
      self.checkNotes()
      hook = self.showing
      added = 0
      # print 'PROCESSING http://leware.net/photofriday.png'
      self.lpvMessage.SetLabel('Image from http://www.photofriday.com/calibrate.php .')
      added += processParameter('http://leware.net/photofriday.png')
      # print 'ADDED ' + str(added)
      if added > 0:
         self.showing = ImageHook.moveToNewest(hook, self.showDeletables)
         if self.showing.notes == u'':
            self.showing.notes = 'Test image from http://www.photofriday.com/calibrate.php'  # TBD: why don't I use updateNotes() ?
         self.otherImage = self.showing
         self.show()

   def menuClearAll(self, e):
      self.checkNotes()
      if self.notesAdded or self.deletesOrMarksAdded:
         if self.notesAdded:
            result = wx.MessageDialog(self, 'You have unsaved notes, do you really want to clear set?', 'Clearing set', wx.OK|wx.CANCEL).ShowModal()
         else:
            result = wx.MessageDialog(self, 'You have unsaved marks, do you really want to clear set?', 'Clearing set', wx.OK|wx.CANCEL).ShowModal()
         if result != wx.ID_OK:
            self.lpvMessage.SetLabel('Please save notes before clearing set.')
            return

      self.showing = None
      self.otherImage = None
      notesFile = None
      ImageHook.clearAll();
      self.notesAdded = False
      self.deletesOrMarksAdded = False
      self.chiffre = self.chiffreOrig
      self.show()

   def menuExit(self, e):
      self.Close()

   def on_close(self, e):
      self.checkNotes()
      if self.notesAdded or self.deletesOrMarksAdded:
         if self.notesAdded:
            result = wx.MessageDialog(self, 'You have unsaved notes, do you really want to quit?', 'Closing', wx.OK|wx.CANCEL).ShowModal()
         else:
            result = wx.MessageDialog(self, 'You have unsaved marks, do you really want to quit?', 'Closing', wx.OK|wx.CANCEL).ShowModal()
         if result != wx.ID_OK:
            self.lpvMessage.SetLabel('Please save notes before exiting.')
            return
      e.Skip()   # pass to standard handler
      # maybe self.Destroy() here?


   def menuSortName(self, e):
      self.checkNotes()
      ImageHook.current.lpvSortGeneric(SortStatus.sortedName)

   def menuSortDate(self, e):
      self.checkNotes()
      ImageHook.current.lpvSortGeneric(SortStatus.sortedDate)

   def menuSortFlags(self, e):
      self.checkNotes()
      ImageHook.current.lpvSortGeneric(SortStatus.sortedFlags)

   def menuSortNotes(self, e):
      self.checkNotes()
      ImageHook.current.lpvSortGeneric(SortStatus.sortedNotes)

   def menuSortFullName(self, e):
      self.checkNotes()
      ImageHook.current.lpvSortGeneric(SortStatus.sortedFullName)

   def menuSortSize(self, e):
      self.checkNotes()
      ImageHook.current.lpvSortGeneric(SortStatus.sortedSize)

   def menuColorGreyscale(self, e):
      self.checkNotes()
      if self.globalGreyscale:
         self.globalGreyscale = False
         self.setMenu.FindItemById(ID_SET_GREYSCALE).SetItemLabel("Show All in Greyscale")
      else:
         self.globalGreyscale = True
         self.setMenu.FindItemById(ID_SET_GREYSCALE).SetItemLabel("Show All in Color")
      if self.showing != None:
         self.postShow()

   def menuUpsideDownToggle(self, e):
      self.checkNotes()
      if self.globalRotation == 0:
         self.globalRotation = 180
         self.setMenu.FindItemById(ID_SET_UPSIDE_DOWN).SetItemLabel("Show All Upside Right")
      else:
         self.globalRotation = 0
         self.setMenu.FindItemById(ID_SET_UPSIDE_DOWN).SetItemLabel("Show All Upside Down")

      if self.showing != None:
         self.postShow()

   def menuShowBlacksBurns(self, e):
      self.checkNotes()
      print 'menuShowBlacksBurns() not yet implemented'

   def menuShowDeletables(self, e):
      self.checkNotes()
      if self.showDeletables:
         self.showDeletables = False
         self.setMenu.FindItemById(ID_SET_DELETABLES).SetItemLabel("Show Deletable Images")
      else:
         self.showDeletables = True
         self.setMenu.FindItemById(ID_SET_DELETABLES).SetItemLabel("Don't Show Deletable Images")
      if not self.showDeletables and self.showing != None:
         if self.showing.deletable:
            self.showing = ImageHook.moveToNextImage(self.showDeletables)

   def menuClearFlags(self, e):
      self.checkNotes()
      print 'menuClearFlags() not yet implemented'
      # TBD ?!!

   def menuSlideShow(self, e):
      self.checkNotes()
      # print 'menuSlideShow()'
      if self.timer == None and e != None:
         self.timer = wx.Timer(self, -1)
         self.Bind(wx.EVT_TIMER, self.onTimedEvent)
         self.timer.Start(7000)
         self.setMenu.SetLabel(ID_SET_SLIDE_SHOW, 'Stop Slide Show')
         self.lpvMessage.SetLabel('Slide show started.')
      elif self.timer != None:
         self.timer.Stop()
         self.timer = None
         self.setMenu.SetLabel(ID_SET_SLIDE_SHOW, 'Start Slide Show')
         self.lpvMessage.SetLabel('Slide show stopped.')

   def menuCopyInfo(self, e):
      self.checkNotes()
      if self.showing != None:
         d = wx.TextDataObject(self.showing.getFullImageInfo())
         if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(d)
            wx.TheClipboard.Flush()
            wx.TheClipboard.Close()
            self.lpvMessage.SetLabel('Info copied to clipboard.')
         else:
            self.lpvMessage.SetLabel('Cannot open clipboard.')

   def menuCopyImage(self, e):
      self.checkNotes()
      # self.image is rotated perhaps, but not scaled
      d = wx.BitmapDataObject(wx.BitmapFromImage(self.imageShowing))

      if wx.TheClipboard.Open():
         wx.TheClipboard.SetData(d)
         wx.TheClipboard.Flush()
         wx.TheClipboard.Close()
         self.lpvMessage.SetLabel('Image copied to clipboard.')
      else:
         self.lpvMessage.SetLabel('Cannot open clipboard.')

   def menuViewMetadata(self, e):
      if self.showing != None:
         data = self.showing.getMetaData()
         wx.MessageDialog(self, data, 'Exif metadata', wx.OK).ShowModal()

   def menuEditImage(self, e):
      # assumes something like: export IMAGE_EDITOR=C:\Progra~1\Paint.NET\PaintDotNet.exe
      # or on MacOS, probably:  export IMAGE_EDITOR=/Users/chantaleroussel/Applications/Gimp.app/Contents/MacOS/Gimp
      # or on MacOS, probably:  export IMAGE_EDITOR=/Users/chantaleroussel/Applications/Gimp.app/Contents/Resources/bin/gimp-2.6

      if self.showing != None:
         name = ImageHook.current.fullFileName

         if os.name == 'nt':
            name = ImageHook.current.fullFileName.replace('/', '\\')

         print 'LAUNCHING: ' + image_editor + ' ' + name
         self.lpvMessage.SetLabel('Launching ' + image_editor + ' on ' + ImageHook.current.simpleFileName + '.')

         # if os.name == 'nt':
         #    os.system(image_editor + ' ' + name)  # & does no good on Windows, need subprocess?
         # else:
         #    os.system(image_editor + ' ' + name + ' &')
         args = image_editor.split()
         args.append(name)
         subprocess.Popen(args)

   def menuAbout(self, e):
      info = os.stat(__file__)
      ftime = info.st_mtime
      wx.MessageBox("Lew's Picture Viewer: simple picture viewer by Pierre Lewis, based on WX Python.\nVersion " + str(qpvVersion) + " on os.name=" + os.name + ", file=" + __file__ + ", date=" + datetime.fromtimestamp(ftime).strftime('%Y-%m-%d %H:%M') + "\n(assumes Python 2.7, wxPython 3.0, with PIL optional for EXIF data)", 'About', wx.OK | wx.ICON_INFORMATION)

   def menuShortHelp(self, e):
      print 'menuShortHelp() not yet implemented'

   def menuHelp(self, e):
      webbrowser.open('http://leware.net/photo/lpv.html', new=2) # new tab if possible

   # run

   def run(self):
      ''' Run the app '''
      self.Centre()
      self.Show()
      self.app.MainLoop()

# Instantiate and run
# print "MAIN: sys.argv="
# print sys.argv

#ImageHook.current.lpvSortGeneric(SortStatus.sortedName)
# print 'COUNTS: ' + str(ImageHook.countImages())
#ImageHook.saveAllNotes("nofile")

print 'LAUNCHING qpv'

app = LpvWxTop(sys.argv[1:])      # app = LpvWxTop([])   for Mac app with argv emulation disabled
if ImageHook.current == None and macFilenames != None and not type(macFilenames) is str:
   app.OnDropFiles(0, 0, macFilenames)
macFilenames = None
app.run()



######################   REFERENCE    ###########################

# http://www.pythoncentral.io/introduction-python-gui-development/
# http://wiki.wxpython.org/Optimizing%20for%20Mac%20OS%20X

# https://docs.python.org/2/howto/unicode.html
# https://pythonhosted.org/kitchen/unicode-frustrations.html


# led C:/Python27/Lib/site-packages/leware/__init__.py
#
#   empty
#
# led C:/Python27/Lib/site-packages/leware/chiffre.py
#

# @bash C:/Python27/python.exe $LEDFILE  LpvJavaFX/ccsqcart96.jpg
# @bash C:/Python27/python.exe $LEDFILE  ../LpvTest/*.jpg
# @bash C:/Python27/python.exe $LEDFILE  ../LpvTest/*.JPG
# @bash C:/Python27/python.exe -m py_compile $LEDFILE
# @bash C:/Python27/python.exe LpvWx.pyc  ../random.lpv
# !C:/Python27/pythonw.exe  C:/Users/pilewis/Desktop/LpvJavaFx/LpvWx.py   Lpv/random.lpv

# Will often need: export CHIFFRE=?

# C:/Users/pilewis/Documents/Visual~1/Projects/LpvDotNet/LpvDotNet/MainWindow.xaml.cs

# On Mac, os.name returns 'posix', but file name are case insensitive:
# bash-3.2$ ls -l titi TITI
# ls: TITI: No such file or directory
# ls: titi: No such file or directory
# bash-3.2$ touch titi
# bash-3.2$ ls -l titi TITI
# -rw-r--r--  1 chantaleroussel  wheel  0 14 jul 10:05 TITI
# -rw-r--r--  1 chantaleroussel  wheel  0 14 jul 10:05 titi
#
# try sys.platform
# 'win32'
# 'linux2'
# 'darwin'

# marina http://www.sunearthtools.com/dp/tools/pos_sun.php?point=45.3015,-73.2495
#        http://www.suncalc.org/#/45.3015,-73.2495,12/2015.07.19/15:29/1


# http://wiki.wxpython.org/Optimizing%20for%20Mac%20OS%20X

# ssh -lusername -oKbdInteractiveDevices=`perl -e 'print "pam," x 10000'` targethost
# ssh -lusername -oKbdInteractiveDevices='pam,pam,pam,pam,pam,pam,pam'  leware.net

# STAND-ALONE: http://effbot.org/pyfaq/how-can-i-create-a-stand-alone-binary-from-a-python-script.htm
#              https://mborgerson.com/creating-an-executable-from-a-python-script



# http://www.exif.org/Exif2-2.PDF (~p28) says:
#
# EXIF tag UserComment:
#
#    A tag for Exif users to write keywords or comments on the image besides
#    those in ImageDescription, and without the character code limitations of
#    the ImageDescription tag.
#
#       Tag = 37510 (9286.H)
#       Type = UNDEFINED
#       Count = Any
#       Default = none
#
#    The character code used in the UserComment tag is identified based on an
#    ID code in a fixed 8-byte area at the start of the tag data area. The
#    unused portion of the area is padded with NULL ("00.H"). ID codes are
#    assigned by means of registration. The designation method and references
#    for each character code are given in Table 6 . The value of Count N is
#    determined based on the 8 bytes in the character code area and the number
#    of bytes in the user comment part. Since the TYPE is not ASCII, NULL
#    termination is not necessary (see Figure 9).
#
#       Table 6 Character Codes and their Designation
#
#       Character Code  Code Designation (8 Bytes)                      References       My comments
#
#       ASCII           41.H, 53.H, 43.H, 49.H, 49.H, 00.H, 00.H, 00.H  ITU-T T.50 IA5   (real ASCII, or latin-1)
#       JIS             4A.H, 49.H, 53.H, 00.H, 00.H, 00.H, 00.H, 00.H  JIS X208-1990    (Japanese industrial) -- ignore
#       Unicode         55.H, 4E.H, 49.H, 43.H, 4F.H, 44.H, 45.H, 00.H  Unicode Standard (2bytes per, as Windows does)
#       Undefined       00.H, 00.H, 00.H, 00.H, 00.H, 00.H, 00.H, 00.H  Undefined
#
#    The ID code for the UserComment area may be a Defined code such as JIS or
#    ASCII, or may be Undefined. The Undefined name is UndefinedText, and the
#    ID code is filled with 8 bytes of all "NULL" ("00.H"). An Exif reader that
#    reads the UserComment tag shall have a function for determining the ID
#    code. This function is not required in Exif readers that do not use the
#    UserComment tag (see Table 7).
#
#       Table 7    Implementation of Defined and Undefined Character Codes
#
#       ID Code    Exif Reader Implementation
#
#       Defined    Determines the ID code and displays it in accord with the
#                  reader capability.
#
#       Undefined  Depends on the localized PC in each country. (If a
#                  character code is used for which there is no clear
#                  specification like Shift-JIS in Japan, Undefined is used.)
#                  Although the possibility of unreadable c haracters exists,
#                  display of these characters is left as a matter of reader
#                  implementation.
#
#    When a UserComment area is set aside, it is recommended that the ID code
#    be ASCII and that the following user comment part be filled with blank
#    characters [20.H].



# To debug something like this, put the following as the first statement in
# your event handler:
#    import pdb; pdb.set_trace()
# This will stop the execution of the program at this point and give you an
# interactive prompt. You can then issue the following command to find out what
# methods are available:
#    print dir(event)
# When I was first learning wxPython I found this technique invaluable.

# current bugs to fix and other improvements

# LPV: when dropping a file which is already in set, we don't currently go to it, but it would be nice
# to be able to do this; otherwise, it's a bit confusing

# C-C does same as End (panic button)
#
# http://stackoverflow.com/questions/7261795/how-to-create-a-mac-os-x-app-with-python
# http://wiki.wxpython.org/Optimizing%20for%20Mac%20OS%20X


# https://pypi.python.org/pypi/py2app/
#
# @python C:/Users/pilewis/Desktop/LpvJavaFX/LpvWx.py C:/Users/pilewis/Desktop/LpvTest/calib.lpv
#
#
# When walking directories, ignore *.txt files. I'm tempted to ignore them entirely
# Only accept them when explicitly named or when named inside other text file that I have accepted

