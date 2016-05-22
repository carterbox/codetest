# -*- coding: utf-8 -*-
########### SVN repository information ###################
# $Date: 2015-04-27 13:22:06 -0500 (Mon, 27 Apr 2015) $
# $Author: vondreele $
# $Revision: 1812 $
# $URL: https://subversion.xray.aps.anl.gov/pyGSAS/trunk/imports/G2phase_GPX.py $
# $Id: G2phase_GPX.py 1812 2015-04-27 18:22:06Z vondreele $
########### SVN repository information ###################
'''
*Module G2phase_INS: Import phase from SHELX INS file*
--------------------------------------------------------

Copies a phase from SHELX ins file into the
current project.

'''
import sys
import traceback
import math
import numpy as np
import random as ran
import GSASIIIO as G2IO
import GSASIIspc as G2spc
import GSASIIlattice as G2lat
import GSASIIpath
GSASIIpath.SetVersionNumber("$Revision: 1812 $")

class PhaseReaderClass(G2IO.ImportPhase):
    'Opens a .INS file and pulls out a selected phase'
    def __init__(self):
        super(self.__class__,self).__init__( # fancy way to say ImportPhase.__init__
            extensionlist=('.ins','.INS'),
            strictExtension=True,
            formatName = 'SHELX ins',
            longFormatName = 'SHELX input (*.ins) file import'
            )
        
    def ContentsValidator(self, filepointer):
        "Test if the ins file has a CELL record"
        for i,l in enumerate(filepointer):
            if l.startswith('CELL'):
                break
        else:
            self.errors = 'no CELL record found'
            self.errors = 'This is not a valid .ins file.'
            return False
        return True

    def Reader(self,filename,filepointer, ParentFrame=None, **unused):
        'Read a ins file using :meth:`ReadINSPhase`'
        try:
            self.Phase = self.ReadINSPhase(filename, ParentFrame)
            return True
        except Exception as detail:
            self.errors += '\n  '+str(detail)
            print 'INS read error:',detail # for testing
            traceback.print_exc(file=sys.stdout)
            return False

    def ReadINSPhase(self,filename,parent=None):
        '''Read a phase from a INS file.
        '''
        EightPiSq = 8.*math.pi**2
        self.errors = 'Error opening file'
        file = open(filename, 'Ur')
        Phase = {}
        Title = ''
        Compnd = ''
        Atoms = []
        aTypes = []
        A = np.zeros(shape=(3,3))
        S = file.readline()
        line = 1
        SGData = None
        cell = None
        numbs = [str(i) for i in range(10)]
        while S:
            if '!' in S:
                S = S.split('!')[0]
            self.errors = 'Error reading at line '+str(line)
            Atom = []
            Aindx = [ch in numbs for ch in S[:4]]   #False for all letters
            if 'TITL' in S[:4]:
                Title = S[4:72].strip()
            elif 'CELL' in S[:4]:
                abc = S[12:40].split()
                angles = S[40:64].split()
                cell=[float(abc[0]),float(abc[1]),float(abc[2]),
                    float(angles[0]),float(angles[1]),float(angles[2])]
                Volume = G2lat.calc_V(G2lat.cell2A(cell))
                AA,AB = G2lat.cell2AB(cell)
                SpGrp = 'P 1'
                SGData = G2IO.SGData # P 1
                self.warnings += '\nThe space group is not given in an ins file and has been set to "P 1".'
                self.warnings += "\nChange this in phase's General tab; NB: it might be in the Phase name."
            elif S[:4] in 'SFAC':
                aTypes = S[4:].split()
                if 'H' in aTypes:
                    self.warnings += '\nHydrogen atoms found; consider replacing them with stereochemically tied ones.'
                    self.warnings += "\nDo 'Edit/Insert H atoms' in this phase's Atoms tab after deleting the old ones."
            elif S[0] == 'Q':
                pass
            elif np.any(Aindx) or S[:4].strip() in aTypes:   #this will find an atom record!
                try:
                    iNum = Aindx.index(True)
                except ValueError:
                    iNum = 4
                Atype = S[:iNum].strip()
                Aname = S[:4]
                x,y,z = S[9:45].split()
                XYZ = np.array([float(x),float(y),float(z)])
                XYZ = np.where(np.abs(XYZ)<0.00001,0,XYZ)
                SytSym,Mult = G2spc.SytSym(XYZ,SGData)
                if '=' not in S:
                    IA = 'I'
                    Uiso = float(S[57:68])
                    if Uiso < 0.:
                        Uiso = 0.025
                    Uij = [0. for i in range(6)]
                else:
                    IA = 'A'
                    Uiso = 0.
                    Ustr = S[57:78].split()
                    S = file.readline()
                    if '!' in S:
                        S = S.split('!')[0]
                    line += 1
                    Ustr += S[6:51].split()
                    Uij = [float(Ustr[i]) for i in range(6)]
                Atom = [Aname,Atype,'',XYZ[0],XYZ[1],XYZ[2],1.0,SytSym,Mult,IA,Uiso]
                Atom += Uij
                Atom.append(ran.randint(0,sys.maxint))
                Atoms.append(Atom)
            S = file.readline()
            line += 1
        file.close()
        self.errors = 'Error after read complete'
        Phase = G2IO.SetNewPhase(Name='ShelX phase',SGData=SGData,cell=cell+[Volume,])
        Phase['General']['Name'] = Title
        Phase['General']['Type'] = 'nuclear'
        Phase['General']['AtomPtrs'] = [3,1,7,9]
        Phase['Atoms'] = Atoms
        return Phase