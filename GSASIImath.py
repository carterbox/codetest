# -*- coding: utf-8 -*-
#GSASIImath - major mathematics routines
########### SVN repository information ###################
# $Date$
# $Author$
# $Revision$
# $URL$
# $Id$
########### SVN repository information ###################
'''
*GSASIImath: computation module*
================================

Routines for least-squares minimization and other stuff

'''
from __future__ import division, print_function
import random as rn
import numpy as np
import numpy.linalg as nl
import numpy.ma as ma
import time
import math
import copy
import GSASIIpath
GSASIIpath.SetVersionNumber("$Revision$")
import GSASIIElem as G2el
import GSASIIlattice as G2lat
import GSASIIspc as G2spc
import GSASIIpwd as G2pwd
import GSASIIfiles as G2fil
import numpy.fft as fft
import scipy.optimize as so
try:
    import pypowder as pwd
except ImportError:
    print ('pypowder is not available - profile calcs. not allowed')

sind = lambda x: np.sin(x*np.pi/180.)
cosd = lambda x: np.cos(x*np.pi/180.)
tand = lambda x: np.tan(x*np.pi/180.)
asind = lambda x: 180.*np.arcsin(x)/np.pi
acosd = lambda x: 180.*np.arccos(x)/np.pi
atand = lambda x: 180.*np.arctan(x)/np.pi
atan2d = lambda y,x: 180.*np.arctan2(y,x)/np.pi
try:  # fails on doc build
    twopi = 2.0*np.pi
    twopisq = 2.0*np.pi**2
    _double_min = np.finfo(float).min
    _double_max = np.finfo(float).max
except TypeError:
    pass
nxs = np.newaxis
    
################################################################################
##### Hessian least-squares Levenberg-Marquardt routine
################################################################################

def pinv(a, rcond=1e-15 ):
    """
    Compute the (Moore-Penrose) pseudo-inverse of a matrix.
    Modified from numpy.linalg.pinv; assumes a is Hessian & returns no. zeros found
    Calculate the generalized inverse of a matrix using its
    singular-value decomposition (SVD) and including all
    *large* singular values.

    :param array a: (M, M) array_like - here assumed to be LS Hessian
      Matrix to be pseudo-inverted.
    :param float rcond: Cutoff for small singular values.
      Singular values smaller (in modulus) than
      `rcond` * largest_singular_value (again, in modulus)
      are set to zero.

    :returns: B : (M, M) ndarray
      The pseudo-inverse of `a`

    Raises: LinAlgError
      If the SVD computation does not converge.

    Notes: 
      The pseudo-inverse of a matrix A, denoted :math:`A^+`, is
      defined as: "the matrix that 'solves' [the least-squares problem]
      :math:`Ax = b`," i.e., if :math:`\\bar{x}` is said solution, then
      :math:`A^+` is that matrix such that :math:`\\bar{x} = A^+b`.

    It can be shown that if :math:`Q_1 \\Sigma Q_2^T = A` is the singular
    value decomposition of A, then
    :math:`A^+ = Q_2 \\Sigma^+ Q_1^T`, where :math:`Q_{1,2}` are
    orthogonal matrices, :math:`\\Sigma` is a diagonal matrix consisting
    of A's so-called singular values, (followed, typically, by
    zeros), and then :math:`\\Sigma^+` is simply the diagonal matrix
    consisting of the reciprocals of A's singular values
    (again, followed by zeros). [1]

    References: 
    .. [1] G. Strang, *Linear Algebra and Its Applications*, 2nd Ed., Orlando, FL, Academic Press, Inc., 1980, pp. 139-142.

    """
    u, s, vt = nl.svd(a)
    cutoff = rcond*np.maximum.reduce(s)
    s = np.where(s>cutoff,1./s,0.)
    nzero = s.shape[0]-np.count_nonzero(s)
#    res = np.dot(np.transpose(vt), np.multiply(s[:, np.newaxis], np.transpose(u)))
    res = np.dot(vt.T,s[:,nxs]*u.T)
    return res,nzero

def HessianLSQ(func,x0,Hess,args=(),ftol=1.49012e-8,xtol=1.e-6, maxcyc=0,lamda=-3,Print=False,refPlotUpdate=None):
    """
    Minimize the sum of squares of a function (:math:`f`) evaluated on a series of
    values (y): :math:`\sum_{y=0}^{N_{obs}} f(y,{args})`    
    where :math:`x = arg min(\sum_{y=0}^{N_{obs}} (func(y)^2,axis=0))`

    :param function func: callable method or function
        should take at least one (possibly length N vector) argument and
        returns M floating point numbers.
    :param np.ndarray x0: The starting estimate for the minimization of length N
    :param function Hess: callable method or function
        A required function or method to compute the weighted vector and Hessian for func.
        It must be a symmetric NxN array
    :param tuple args: Any extra arguments to func are placed in this tuple.
    :param float ftol: Relative error desired in the sum of squares.
    :param float xtol: Relative tolerance of zeros in the SVD solution in nl.pinv.
    :param int maxcyc: The maximum number of cycles of refinement to execute, if -1 refine 
        until other limits are met (ftol, xtol)
    :param int lamda: initial Marquardt lambda=10**lamda 
    :param bool Print: True for printing results (residuals & times) by cycle

    :returns: (x,cov_x,infodict) where

      * x : ndarray
        The solution (or the result of the last iteration for an unsuccessful
        call).
      * cov_x : ndarray
        Uses the fjac and ipvt optional outputs to construct an
        estimate of the jacobian around the solution.  ``None`` if a
        singular matrix encountered (indicates very flat curvature in
        some direction).  This matrix must be multiplied by the
        residual standard deviation to get the covariance of the
        parameter estimates -- see curve_fit.
      * infodict : dict
        a dictionary of optional outputs with the keys:

         * 'fvec' : the function evaluated at the output
         * 'num cyc':
         * 'nfev':
         * 'lamMax':
         * 'psing':
         * 'SVD0':
            
    """
                
    ifConverged = False
    deltaChi2 = -10.
    x0 = np.array(x0, ndmin=1)      #might be redundant?
    n = len(x0)
    if type(args) != type(()):
        args = (args,)
        
    icycle = 0
    One = np.ones((n,n))
    lam = 10.**lamda
    lamMax = lam
    nfev = 0
    if Print:
        G2fil.G2Print(' Hessian Levenberg-Marquardt SVD refinement on %d variables:'%(n))
    Lam = np.zeros((n,n))
    while icycle < maxcyc:
        time0 = time.time()
        M = func(x0,*args)
        Nobs = len(M)
        nfev += 1
        chisq0 = np.sum(M**2)
        Yvec,Amat = Hess(x0,*args)
        Adiag = np.sqrt(np.diag(Amat))
        psing = np.where(np.abs(Adiag) < 1.e-14,True,False)
        if np.any(psing):                #hard singularity in matrix
            return [x0,None,{'num cyc':icycle,'fvec':M,'nfev':nfev,'lamMax':lamMax,'psing':psing,'SVD0':-1}]
        Anorm = np.outer(Adiag,Adiag)
        Yvec /= Adiag
        Amat /= Anorm
        if Print:
            G2fil.G2Print('initial chi^2 %.5g on %d obs.'%(chisq0,Nobs))
        chitol = ftol
        while True:
            Lam = np.eye(Amat.shape[0])*lam
            Amatlam = Amat*(One+Lam)
            try:
                Ainv,Nzeros = pinv(Amatlam,xtol)    #do Moore-Penrose inversion (via SVD)
            except nl.LinAlgError:
                psing = list(np.where(np.diag(nl.qr(Amatlam)[1]) < 1.e-14)[0])
                G2fil.G2Print('ouch #1 bad SVD inversion; change parameterization for ',psing, mode='error')
                return [x0,None,{'num cyc':icycle,'fvec':M,'nfev':nfev,'lamMax':lamMax,'psing':psing,'SVD0':-1}]
            Xvec = np.inner(Ainv,Yvec)      #solve
            Xvec /= Adiag
            M2 = func(x0+Xvec,*args)
            nfev += 1
            chisq1 = np.sum(M2**2)
            if chisq1 > chisq0*(1.+chitol):     #TODO put Alan Coehlo's criteria for lambda here?
                lam *= 10.
                if Print:
                    G2fil.G2Print('new chi^2 %.5g on %d obs., %d SVD zeros ; matrix modification needed; lambda now %.1e'  \
                           %(chisq1,Nobs,Nzeros,lam))
            else:
                x0 += Xvec
                lam /= 10.
                break
            if lam > 10.:
                G2fil.G2Print('ouch #3 chisq1 %g.4 stuck > chisq0 %g.4'%(chisq1,chisq0), mode='warn')
                break
            chitol *= 2
        lamMax = max(lamMax,lam)
        deltaChi2 = (chisq0-chisq1)/chisq0
        if Print:
            G2fil.G2Print(' Cycle: %d, Time: %.2fs, Chi**2: %.5g for %d obs., Lambda: %.3g,  Delta: %.3g'%(
                icycle,time.time()-time0,chisq1,Nobs,lamMax,deltaChi2))
        Histograms = args[0][0]
        if refPlotUpdate is not None: refPlotUpdate(Histograms,icycle)   # update plot
        if deltaChi2 < ftol:
            ifConverged = True
            if Print: G2fil.G2Print("converged")
            break
        icycle += 1
    M = func(x0,*args)
    nfev += 1
    Yvec,Amat = Hess(x0,*args)
    Adiag = np.sqrt(np.diag(Amat))
    Anorm = np.outer(Adiag,Adiag)
    Lam = np.eye(Amat.shape[0])*lam
    Amatlam = Amat/Anorm        
    try:
        Bmat,Nzero = pinv(Amatlam,xtol)    #Moore-Penrose inversion (via SVD) & count of zeros
        if Print: G2fil.G2Print('Found %d SVD zeros'%(Nzero), mode='warn')
        Bmat = Bmat/Anorm
        return [x0,Bmat,{'num cyc':icycle,'fvec':M,'nfev':nfev,'lamMax':lamMax,'psing':[],
            'SVD0':Nzero,'Converged': ifConverged, 'DelChi2':deltaChi2,'Xvec':Xvec}]
    except nl.LinAlgError:
        G2fil.G2Print('ouch #2 linear algebra error in making v-cov matrix', mode='error')
        psing = []
        if maxcyc:
            psing = list(np.where(np.diag(nl.qr(Amat)[1]) < 1.e-14)[0])
        return [x0,None,{'num cyc':icycle,'fvec':M,'nfev':nfev,'lamMax':lamMax,'psing':psing,'SVD0':-1,'Xvec':None}]          
            
def HessianSVD(func,x0,Hess,args=(),ftol=1.49012e-8,xtol=1.e-6, maxcyc=0,lamda=-3,Print=False,refPlotUpdate=None):
    
    """
    Minimize the sum of squares of a function (:math:`f`) evaluated on a series of
    values (y): :math:`\sum_{y=0}^{N_{obs}} f(y,{args})`    
    where :math:`x = arg min(\sum_{y=0}^{N_{obs}} (func(y)^2,axis=0))`

    :param function func: callable method or function
        should take at least one (possibly length N vector) argument and
        returns M floating point numbers.
    :param np.ndarray x0: The starting estimate for the minimization of length N
    :param function Hess: callable method or function
        A required function or method to compute the weighted vector and Hessian for func.
        It must be a symmetric NxN array
    :param tuple args: Any extra arguments to func are placed in this tuple.
    :param float ftol: Relative error desired in the sum of squares.
    :param float xtol: Relative tolerance of zeros in the SVD solution in nl.pinv.
    :param int maxcyc: The maximum number of cycles of refinement to execute, if -1 refine 
        until other limits are met (ftol, xtol)
    :param bool Print: True for printing results (residuals & times) by cycle

    :returns: (x,cov_x,infodict) where

      * x : ndarray
        The solution (or the result of the last iteration for an unsuccessful
        call).
      * cov_x : ndarray
        Uses the fjac and ipvt optional outputs to construct an
        estimate of the jacobian around the solution.  ``None`` if a
        singular matrix encountered (indicates very flat curvature in
        some direction).  This matrix must be multiplied by the
        residual standard deviation to get the covariance of the
        parameter estimates -- see curve_fit.
      * infodict : dict
        a dictionary of optional outputs with the keys:

         * 'fvec' : the function evaluated at the output
         * 'num cyc':
         * 'nfev':
         * 'lamMax':0.
         * 'psing':
         * 'SVD0':
            
    """
                
    ifConverged = False
    deltaChi2 = -10.
    x0 = np.array(x0, ndmin=1)      #might be redundant?
    n = len(x0)
    if type(args) != type(()):
        args = (args,)
        
    icycle = 0
    nfev = 0
    if Print:
        G2fil.G2Print(' Hessian SVD refinement on %d variables:'%(n))
    while icycle < maxcyc:
        time0 = time.time()
        M = func(x0,*args)
        nfev += 1
        chisq0 = np.sum(M**2)
        Yvec,Amat = Hess(x0,*args)
        Adiag = np.sqrt(np.diag(Amat))
        psing = np.where(np.abs(Adiag) < 1.e-14,True,False)
        if np.any(psing):                #hard singularity in matrix
            return [x0,None,{'num cyc':icycle,'fvec':M,'nfev':nfev,'lamMax':0.,'psing':psing,'SVD0':-1}]
        Anorm = np.outer(Adiag,Adiag)
        Yvec /= Adiag
        Amat /= Anorm
        if Print:
            G2fil.G2Print('initial chi^2 %.5g'%(chisq0))
        try:
            Ainv,Nzeros = pinv(Amat,xtol)    #do Moore-Penrose inversion (via SVD)
        except nl.LinAlgError:
            G2fil.G2Print('ouch #1 bad SVD inversion; change parameterization', mode='warn')
            psing = list(np.where(np.diag(nl.qr(Amat)[1]) < 1.e-14)[0])
            return [x0,None,{'num cyc':icycle,'fvec':M,'nfev':nfev,'lamMax':0.,'psing':psing,'SVD0':-1}]
        Xvec = np.inner(Ainv,Yvec)      #solve
        Xvec /= Adiag
        M2 = func(x0+Xvec,*args)
        nfev += 1
        chisq1 = np.sum(M2**2)
        deltaChi2 = (chisq0-chisq1)/chisq0
        if Print:
            G2fil.G2Print(' Cycle: %d, Time: %.2fs, Chi**2: %.5g, Delta: %.3g'%(
                icycle,time.time()-time0,chisq1,deltaChi2))
        Histograms = args[0][0]
        if refPlotUpdate is not None: refPlotUpdate(Histograms,icycle)   # update plot
        if deltaChi2 < ftol:
            ifConverged = True
            if Print: G2fil.G2Print("converged")
            break
        icycle += 1
    M = func(x0,*args)
    nfev += 1
    Yvec,Amat = Hess(x0,*args)
    Adiag = np.sqrt(np.diag(Amat))
    Anorm = np.outer(Adiag,Adiag)
    Amat = Amat/Anorm        
    try:
        Bmat,Nzero = pinv(Amat,xtol)    #Moore-Penrose inversion (via SVD) & count of zeros
        G2fil.G2Print('Found %d SVD zeros'%(Nzero), mode='warn')
#        Bmat = nl.inv(Amatlam); Nzeros = 0
        Bmat = Bmat/Anorm
        return [x0,Bmat,{'num cyc':icycle,'fvec':M,'nfev':nfev,'lamMax':0.,'psing':[],
            'SVD0':Nzero,'Converged': ifConverged, 'DelChi2':deltaChi2}]
    except nl.LinAlgError:
        G2fil.G2Print('ouch #2 linear algebra error in making v-cov matrix', mode='error')
        psing = []
        if maxcyc:
            psing = list(np.where(np.diag(nl.qr(Amat)[1]) < 1.e-14)[0])
        return [x0,None,{'num cyc':icycle,'fvec':M,'nfev':nfev,'lamMax':0.,'psing':psing,'SVD0':-1}]          
            
def getVCov(varyNames,varyList,covMatrix):
    '''obtain variance-covariance terms for a set of variables. NB: the varyList 
    and covMatrix were saved by the last least squares refinement so they must match.
    
    :param list varyNames: variable names to find v-cov matric for
    :param list varyList: full list of all variables in v-cov matrix
    :param nparray covMatrix: full variance-covariance matrix from the last 
     least squares refinement
    
    :returns: nparray vcov: variance-covariance matrix for the variables given
     in varyNames
    
    '''
    vcov = np.zeros((len(varyNames),len(varyNames)))
    for i1,name1 in enumerate(varyNames):
        for i2,name2 in enumerate(varyNames):
            try:
                vcov[i1][i2] = covMatrix[varyList.index(name1)][varyList.index(name2)]
            except ValueError:
                vcov[i1][i2] = 0.0
#                if i1 == i2:
#                    vcov[i1][i2] = 1e-20
#                else: 
#                    vcov[i1][i2] = 0.0
    return vcov
    
################################################################################
##### Atom manipulations
################################################################################

def FindMolecule(ind,generalData,atomData):                    #uses numpy & masks - very fast even for proteins!

    def getNeighbors(atom,radius):
        Dx = UAtoms-np.array(atom[cx:cx+3])
        dist = ma.masked_less(np.sqrt(np.sum(np.inner(Amat,Dx)**2,axis=0)),0.5) #gets rid of disorder "bonds" < 0.5A
        sumR = Radii+radius
        return set(ma.nonzero(ma.masked_greater(dist-factor*sumR,0.))[0])                #get indices of bonded atoms

    import numpy.ma as ma
    indices = (-1,0,1)
    Units = np.array([[h,k,l] for h in indices for k in indices for l in indices],dtype='f')
    cx,ct,cs,ci = generalData['AtomPtrs']
    DisAglCtls = generalData['DisAglCtls']
    SGData = generalData['SGData']
    Amat,Bmat = G2lat.cell2AB(generalData['Cell'][1:7])
    radii = DisAglCtls['BondRadii']
    atomTypes = DisAglCtls['AtomTypes']
    factor = DisAglCtls['Factors'][0]
    unit = np.zeros(3)
    try:
        indH = atomTypes.index('H')
        radii[indH] = 0.5
    except:
        pass            
    nAtom = len(atomData)
    Indx = list(range(nAtom))
    UAtoms = []
    Radii = []
    for atom in atomData:
        UAtoms.append(np.array(atom[cx:cx+3]))
        Radii.append(radii[atomTypes.index(atom[ct])])
    UAtoms = np.array(UAtoms)
    Radii = np.array(Radii)
    for nOp,Op in enumerate(SGData['SGOps'][1:]):
        UAtoms = np.concatenate((UAtoms,(np.inner(Op[0],UAtoms[:nAtom]).T+Op[1])))
        Radii = np.concatenate((Radii,Radii[:nAtom]))
        Indx += Indx[:nAtom]
    for icen,cen in enumerate(SGData['SGCen'][1:]):
        UAtoms = np.concatenate((UAtoms,(UAtoms+cen)))
        Radii = np.concatenate((Radii,Radii))
        Indx += Indx[:nAtom]
    if SGData['SGInv']:
        UAtoms = np.concatenate((UAtoms,-UAtoms))
        Radii = np.concatenate((Radii,Radii))
        Indx += Indx
    UAtoms %= 1.
    mAtoms = len(UAtoms)
    for unit in Units:
        if np.any(unit):    #skip origin cell
            UAtoms = np.concatenate((UAtoms,UAtoms[:mAtoms]+unit))
            Radii = np.concatenate((Radii,Radii[:mAtoms]))
            Indx += Indx[:mAtoms]
    UAtoms = np.array(UAtoms)
    Radii = np.array(Radii)
    newAtoms = [atomData[ind],]
    atomData[ind] = None
    radius = Radii[ind]
    IndB = getNeighbors(newAtoms[-1],radius)
    while True:
        if not len(IndB):
            break
        indb = IndB.pop()
        if atomData[Indx[indb]] == None:
            continue
        while True:
            try:
                jndb = IndB.index(indb)
                IndB.remove(jndb)
            except:
                break
        newAtom = copy.copy(atomData[Indx[indb]])
        newAtom[cx:cx+3] = UAtoms[indb]     #NB: thermal Uij, etc. not transformed!
        newAtoms.append(newAtom)
        atomData[Indx[indb]] = None
        IndB = set(list(IndB)+list(getNeighbors(newAtoms[-1],radius)))
        if len(IndB) > nAtom:
            return 'Assemble molecule cannot be used on extended structures'
    for atom in atomData:
        if atom != None:
            newAtoms.append(atom)
    return newAtoms
        
def FindAtomIndexByIDs(atomData,loc,IDs,Draw=True):
    '''finds the set of atom array indices for a list of atom IDs. Will search 
    either the Atom table or the drawAtom table.
    
    :param list atomData: Atom or drawAtom table containting coordinates, etc.
    :param int loc: location of atom id in atomData record
    :param list IDs: atom IDs to be found
    :param bool Draw: True if drawAtom table to be searched; False if Atom table
      is searched
    
    :returns: list indx: atom (or drawAtom) indices
    
    '''
    indx = []
    for i,atom in enumerate(atomData):
        if Draw and atom[loc] in IDs:
            indx.append(i)
        elif atom[loc] in IDs:
            indx.append(i)
    return indx

def FillAtomLookUp(atomData,indx):
    '''create a dictionary of atom indexes with atom IDs as keys
    
    :param list atomData: Atom table to be used
    
    :returns: dict atomLookUp: dictionary of atom indexes with atom IDs as keys
    
    '''
    atomLookUp = {}
    for iatm,atom in enumerate(atomData):
        atomLookUp[atom[indx]] = iatm
    return atomLookUp

def GetAtomsById(atomData,atomLookUp,IdList):
    '''gets a list of atoms from Atom table that match a set of atom IDs
    
    :param list atomData: Atom table to be used
    :param dict atomLookUp: dictionary of atom indexes with atom IDs as keys
    :param list IdList: atom IDs to be found
    
    :returns: list atoms: list of atoms found
    
    '''
    atoms = []
    for Id in IdList:
        atoms.append(atomData[atomLookUp[Id]])
    return atoms
    
def GetAtomItemsById(atomData,atomLookUp,IdList,itemLoc,numItems=1):
    '''gets atom parameters for atoms using atom IDs
    
    :param list atomData: Atom table to be used
    :param dict atomLookUp: dictionary of atom indexes with atom IDs as keys
    :param list IdList: atom IDs to be found
    :param int itemLoc: pointer to desired 1st item in an atom table entry
    :param int numItems: number of items to be retrieved
    
    :returns: type name: description
    
    '''
    Items = []
    if not isinstance(IdList,list):
        IdList = [IdList,]
    for Id in IdList:
        if numItems == 1:
            Items.append(atomData[atomLookUp[Id]][itemLoc])
        else:
            Items.append(atomData[atomLookUp[Id]][itemLoc:itemLoc+numItems])
    return Items
    
def GetAtomCoordsByID(pId,parmDict,AtLookup,indx):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    pfx = [str(pId)+'::A'+i+':' for i in ['x','y','z']]
    dpfx = [str(pId)+'::dA'+i+':' for i in ['x','y','z']]
    XYZ = []
    for ind in indx:
        names = [pfx[i]+str(AtLookup[ind]) for i in range(3)]
        dnames = [dpfx[i]+str(AtLookup[ind]) for i in range(3)]
        XYZ.append([parmDict[name]+parmDict[dname] for name,dname in zip(names,dnames)])
    return XYZ
    
def GetAtomFracByID(pId,parmDict,AtLookup,indx):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    pfx = str(pId)+'::Afrac:'
    Frac = []
    for ind in indx:
        name = pfx+str(AtLookup[ind])
        Frac.append(parmDict[name])
    return Frac
    
#    for Atom in Atoms:
#        XYZ = Atom[cx:cx+3]
#        if 'A' in Atom[cia]:
#            U6 = Atom[cia+2:cia+8]
    

def ApplySeqData(data,seqData):
    '''Applies result from seq. refinement to drawing atom positions & Uijs
    '''
    generalData = data['General']
    SGData = generalData['SGData']
    cx,ct,cs,cia = generalData['AtomPtrs']
    drawingData = data['Drawing']
    dcx,dct,dcs,dci = drawingData['atomPtrs']
    atoms = data['Atoms']
    drawAtoms = drawingData['Atoms']
    pId = data['pId']
    pfx = '%d::'%(pId)
    parmDict = seqData['parmDict']
    for ia,atom in enumerate(atoms):
        dxyz = np.array([parmDict[pfx+'dAx:'+str(ia)],parmDict[pfx+'dAy:'+str(ia)],parmDict[pfx+'dAz:'+str(ia)]])
        if atom[cia] == 'A':
            atuij = np.array([parmDict[pfx+'AU11:'+str(ia)],parmDict[pfx+'AU22:'+str(ia)],parmDict[pfx+'AU33:'+str(ia)],
                parmDict[pfx+'AU12:'+str(ia)],parmDict[pfx+'AU13:'+str(ia)],parmDict[pfx+'AU23:'+str(ia)]])
        else:
            atuiso = parmDict[pfx+'AUiso:'+str(ia)]
        atxyz = G2spc.MoveToUnitCell(np.array(atom[cx:cx+3])+dxyz)[0]
        indx = FindAtomIndexByIDs(drawAtoms,dci,[atom[cia+8],],True)
        for ind in indx:
            drawatom = drawAtoms[ind]
            opr = drawatom[dcs-1]
            #how do I handle Sfrac? - fade the atoms?
            if atom[cia] == 'A':                    
                X,U = G2spc.ApplyStringOps(opr,SGData,atxyz,atuij)
                drawatom[dcx:dcx+3] = X
                drawatom[dci-6:dci] = U
            else:
                X = G2spc.ApplyStringOps(opr,SGData,atxyz)
                drawatom[dcx:dcx+3] = X
                drawatom[dci-7] = atuiso
    return drawAtoms
    
def FindNeighbors(phase,FrstName,AtNames,notName=''):
    General = phase['General']
    cx,ct,cs,cia = General['AtomPtrs']
    Atoms = phase['Atoms']
    atNames = [atom[ct-1] for atom in Atoms]
    Cell = General['Cell'][1:7]
    Amat,Bmat = G2lat.cell2AB(Cell)
    atTypes = General['AtomTypes']
    Radii = np.array(General['BondRadii'])
    DisAglCtls = General['DisAglCtls']    
    radiusFactor = DisAglCtls['Factors'][0]
    AtInfo = dict(zip(atTypes,Radii)) #or General['BondRadii']
    Orig = atNames.index(FrstName)
    OId = Atoms[Orig][cia+8]
    OType = Atoms[Orig][ct]
    XYZ = getAtomXYZ(Atoms,cx)        
    Neigh = []
    Ids = []
    Dx = np.inner(Amat,XYZ-XYZ[Orig]).T
    dist = np.sqrt(np.sum(Dx**2,axis=1))
    sumR = np.array([AtInfo[OType]+AtInfo[atom[ct]] for atom in Atoms])
    IndB = ma.nonzero(ma.masked_greater(dist-radiusFactor*sumR,0.))
    for j in IndB[0]:
        if j != Orig:
            if AtNames[j] != notName:
                Neigh.append([AtNames[j],dist[j],True])
                Ids.append(Atoms[j][cia+8])
    return Neigh,[OId,Ids]

def FindOctahedron(results):
    Octahedron = np.array([[1.,0,0],[0,1.,0],[0,0,1.],[-1.,0,0],[0,-1.,0],[0,0,-1.]])
    Polygon = np.array([result[3] for result in results])
    Dists = np.array([np.sqrt(np.sum(axis**2)) for axis in Polygon])
    bond = np.mean(Dists)
    std = np.std(Dists)
    Norms = Polygon/Dists[:,nxs]
    Tilts = acosd(np.dot(Norms,Octahedron[0]))
    iAng = np.argmin(Tilts)
    Qavec = np.cross(Norms[iAng],Octahedron[0])
    QA = AVdeg2Q(Tilts[iAng],Qavec)
    newNorms = prodQVQ(QA,Norms)
    Rots = acosd(np.dot(newNorms,Octahedron[1]))
    jAng = np.argmin(Rots)
    Qbvec = np.cross(Norms[jAng],Octahedron[1])
    QB = AVdeg2Q(Rots[jAng],Qbvec)
    QQ = prodQQ(QA,QB)    
    newNorms = prodQVQ(QQ,Norms)
    dispVecs = np.array([norm[:,nxs]-Octahedron.T for norm in newNorms])
    disp = np.sqrt(np.sum(dispVecs**2,axis=1))
    dispids = np.argmin(disp,axis=1)
    vecDisp = np.array([dispVecs[i,:,dispid] for i,dispid in enumerate(dispids)])
    Disps = np.array([disp[i,dispid] for i,dispid in enumerate(dispids)])
    meanDisp = np.mean(Disps)
    stdDisp = np.std(Disps)
    A,V = Q2AVdeg(QQ)
    return bond,std,meanDisp,stdDisp,A,V,vecDisp
    
def FindTetrahedron(results):
    Tetrahedron = np.array([[1.,1,1],[1,-1,-1],[-1,1,-1],[-1,-1,1]])/np.sqrt(3.)
    Polygon = np.array([result[3] for result in results])
    Dists = np.array([np.sqrt(np.sum(axis**2)) for axis in Polygon])
    bond = np.mean(Dists)
    std = np.std(Dists)
    Norms = Polygon/Dists[:,nxs]
    Tilts = acosd(np.dot(Norms,Tetrahedron[0]))
    iAng = np.argmin(Tilts)
    Qavec = np.cross(Norms[iAng],Tetrahedron[0])
    QA = AVdeg2Q(Tilts[iAng],Qavec)
    newNorms = prodQVQ(QA,Norms)
    Rots = acosd(np.dot(newNorms,Tetrahedron[1]))
    jAng = np.argmin(Rots)
    Qbvec = np.cross(Norms[jAng],Tetrahedron[1])
    QB = AVdeg2Q(Rots[jAng],Qbvec)
    QQ = prodQQ(QA,QB)    
    newNorms = prodQVQ(QQ,Norms)
    dispVecs = np.array([norm[:,nxs]-Tetrahedron.T for norm in newNorms])
    disp = np.sqrt(np.sum(dispVecs**2,axis=1))
    dispids = np.argmin(disp,axis=1)
    vecDisp = np.array([dispVecs[i,:,dispid] for i,dispid in enumerate(dispids)])
    Disps = np.array([disp[i,dispid] for i,dispid in enumerate(dispids)])
    meanDisp = np.mean(Disps)
    stdDisp = np.std(Disps)
    A,V = Q2AVdeg(QQ)
    return bond,std,meanDisp,stdDisp,A,V,vecDisp
    
def FindAllNeighbors(phase,FrstName,AtNames,notName=''):
    General = phase['General']
    cx,ct,cs,cia = General['AtomPtrs']
    Atoms = phase['Atoms']
    atNames = [atom[ct-1] for atom in Atoms]
    atTypes = [atom[ct] for atom in Atoms]
    Cell = General['Cell'][1:7]
    Amat,Bmat = G2lat.cell2AB(Cell)
    SGData = General['SGData']
    indices = (-1,0,1)
    Units = np.array([[h,k,l] for h in indices for k in indices for l in indices])
    AtTypes = General['AtomTypes']
    Radii = np.array(General['BondRadii'])
    DisAglCtls = General['DisAglCtls']    
    radiusFactor = DisAglCtls['Factors'][0]
    AtInfo = dict(zip(AtTypes,Radii)) #or General['BondRadii']
    Orig = atNames.index(FrstName)
    OId = Atoms[Orig][cia+8]
    OType = Atoms[Orig][ct]
    XYZ = getAtomXYZ(Atoms,cx)        
    Oxyz = XYZ[Orig]
    Neigh = []
    Ids = []
    sumR = np.array([AtInfo[OType]+AtInfo[atom[ct]] for atom in Atoms])
    sumR = np.reshape(np.tile(sumR,27),(27,-1))
    results = []
    for xyz in XYZ:
        results.append(G2spc.GenAtom(xyz,SGData,False,Move=False))
    for iA,result in enumerate(results):
        if iA != Orig:                
            for [Txyz,Top,Tunit,Spn] in result:
                Dx = np.array([Txyz-Oxyz+unit for unit in Units])
                dx = np.inner(Dx,Amat)
                dist = np.sqrt(np.sum(dx**2,axis=1))
                IndB = ma.nonzero(ma.masked_greater(dist-radiusFactor*sumR[:,iA],0.))
                for iU in IndB[0]:
                    if AtNames[iA] != notName:
                        unit = Units[iU]
                        if np.any(unit):
                            Topstr = ' +(%4d)[%2d,%2d,%2d]'%(Top,unit[0],unit[1],unit[2])
                        else:
                            Topstr = ' +(%4d)'%(Top)
                        Neigh.append([AtNames[iA]+Topstr,atTypes[iA],dist[iU],dx[iU]])
                        Ids.append(Atoms[iA][cia+8])
    return Neigh,[OId,Ids]
    
def calcBond(A,Ax,Bx,MTCU):
    cell = G2lat.A2cell(A)
    Amat,Bmat = G2lat.cell2AB(cell)
    M,T,C,U = MTCU
    Btx = np.inner(M,Bx)+T+C+U
    Dx = Btx-Ax
    dist = np.sqrt(np.inner(Amat,Dx))
    return dist
    
def AddHydrogens(AtLookUp,General,Atoms,AddHydId):
    
    def getTransMat(RXYZ,OXYZ,TXYZ,Amat):
        Vec = np.inner(Amat,np.array([OXYZ-TXYZ[0],RXYZ-TXYZ[0]])).T            
        Vec /= np.sqrt(np.sum(Vec**2,axis=1))[:,nxs]
        Mat2 = np.cross(Vec[0],Vec[1])      #UxV
        Mat2 /= np.sqrt(np.sum(Mat2**2))
        Mat3 = np.cross(Mat2,Vec[0])        #(UxV)xU
        return nl.inv(np.array([Vec[0],Mat2,Mat3]))        
    
    cx,ct,cs,cia = General['AtomPtrs']
    Cell = General['Cell'][1:7]
    Amat,Bmat = G2lat.cell2AB(Cell)
    nBonds = AddHydId[-1]+len(AddHydId[1])
    Oatom = GetAtomsById(Atoms,AtLookUp,[AddHydId[0],])[0]
    OXYZ = np.array(Oatom[cx:cx+3])
    if 'I' in Oatom[cia]:
        Uiso = Oatom[cia+1]
    else:
        Uiso = (Oatom[cia+2]+Oatom[cia+3]+Oatom[cia+4])/3.0       #simple average
    Uiso = max(Uiso,0.005)                      #set floor!
    Tatoms = GetAtomsById(Atoms,AtLookUp,AddHydId[1])
    TXYZ = np.array([tatom[cx:cx+3] for tatom in Tatoms]) #3 x xyz
    if nBonds == 4:
        if AddHydId[-1] == 1:
            Vec = TXYZ-OXYZ
            Len = np.sqrt(np.sum(np.inner(Amat,Vec).T**2,axis=0))
            Vec = np.sum(Vec/Len,axis=0)
            Len = np.sqrt(np.sum(Vec**2))
            Hpos = OXYZ-0.98*np.inner(Bmat,Vec).T/Len
            HU = 1.1*Uiso
            return [Hpos,],[HU,]
        elif AddHydId[-1] == 2:
            Vec = np.inner(Amat,TXYZ-OXYZ).T
            Vec[0] += Vec[1]            #U - along bisector
            Vec /= np.sqrt(np.sum(Vec**2,axis=1))[:,nxs]
            Mat2 = np.cross(Vec[0],Vec[1])      #UxV
            Mat2 /= np.sqrt(np.sum(Mat2**2))
            Mat3 = np.cross(Mat2,Vec[0])        #(UxV)xU
            iMat = nl.inv(np.array([Vec[0],Mat2,Mat3]))
            Hpos = np.array([[-0.97*cosd(54.75),0.97*sind(54.75),0.],
                [-0.97*cosd(54.75),-0.97*sind(54.75),0.]])
            HU = 1.2*Uiso*np.ones(2)
            Hpos = np.inner(Bmat,np.inner(iMat,Hpos).T).T+OXYZ
            return Hpos,HU
        else:
            Ratom = GetAtomsById(Atoms,AtLookUp,[AddHydId[2],])[0]
            RXYZ = np.array(Ratom[cx:cx+3])
            iMat = getTransMat(RXYZ,OXYZ,TXYZ,Amat)
            a = 0.96*cosd(70.5)
            b = 0.96*sind(70.5)
            Hpos = np.array([[a,0.,-b],[a,-b*cosd(30.),0.5*b],[a,b*cosd(30.),0.5*b]])
            Hpos = np.inner(Bmat,np.inner(iMat,Hpos).T).T+OXYZ
            HU = 1.5*Uiso*np.ones(3)
            return Hpos,HU          
    elif nBonds == 3:
        if AddHydId[-1] == 1:
            Vec = np.sum(TXYZ-OXYZ,axis=0)                
            Len = np.sqrt(np.sum(np.inner(Amat,Vec).T**2))
            Vec = -0.93*Vec/Len
            Hpos = OXYZ+Vec
            HU = 1.1*Uiso
            return [Hpos,],[HU,]
        elif AddHydId[-1] == 2:
            Ratom = GetAtomsById(Atoms,AtLookUp,[AddHydId[2],])[0]
            RXYZ = np.array(Ratom[cx:cx+3])
            iMat = getTransMat(RXYZ,OXYZ,TXYZ,Amat)
            a = 0.93*cosd(60.)
            b = 0.93*sind(60.)
            Hpos = [[a,b,0],[a,-b,0]]
            Hpos = np.inner(Bmat,np.inner(iMat,Hpos).T).T+OXYZ
            HU = 1.2*Uiso*np.ones(2)
            return Hpos,HU
    else:   #2 bonds
        if 'C' in Oatom[ct]:
            Vec = TXYZ[0]-OXYZ
            Len = np.sqrt(np.sum(np.inner(Amat,Vec).T**2))
            Vec = -0.93*Vec/Len
            Hpos = OXYZ+Vec
            HU = 1.1*Uiso
            return [Hpos,],[HU,]
        elif 'O' in Oatom[ct]:
            mapData = General['Map']
            Ratom = GetAtomsById(Atoms,AtLookUp,[AddHydId[2],])[0]
            RXYZ = np.array(Ratom[cx:cx+3])
            iMat = getTransMat(RXYZ,OXYZ,TXYZ,Amat)
            a = 0.82*cosd(70.5)
            b = 0.82*sind(70.5)
            azm = np.arange(0.,360.,5.)
            Hpos = np.array([[a,b*cosd(x),b*sind(x)] for x in azm])
            Hpos = np.inner(Bmat,np.inner(iMat,Hpos).T).T+OXYZ
            Rhos = np.array([getRho(pos,mapData) for pos in Hpos])
            imax = np.argmax(Rhos)
            HU = 1.5*Uiso
            return [Hpos[imax],],[HU,]
    return [],[]
        
#def AtomUij2TLS(atomData,atPtrs,Amat,Bmat,rbObj):   #unfinished & not used
#    '''default doc string
#    
#    :param type name: description
#    
#    :returns: type name: description
#    
#    '''
#    for atom in atomData:
#        XYZ = np.inner(Amat,atom[cx:cx+3])
#        if atom[cia] == 'A':
#            UIJ = atom[cia+2:cia+8]
                
def TLS2Uij(xyz,g,Amat,rbObj):    #not used anywhere, but could be?
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    TLStype,TLS = rbObj['ThermalMotion'][:2]
    Tmat = np.zeros((3,3))
    Lmat = np.zeros((3,3))
    Smat = np.zeros((3,3))
    gvec = np.sqrt(np.array([g[0][0]**2,g[1][1]**2,g[2][2]**2,
        g[0][0]*g[1][1],g[0][0]*g[2][2],g[1][1]*g[2][2]]))
    if 'T' in TLStype:
        Tmat = G2lat.U6toUij(TLS[:6])
    if 'L' in TLStype:
        Lmat = G2lat.U6toUij(TLS[6:12])
    if 'S' in TLStype:
        Smat = np.array([[TLS[18],TLS[12],TLS[13]],[TLS[14],TLS[19],TLS[15]],[TLS[16],TLS[17],0] ])
    XYZ = np.inner(Amat,xyz)
    Axyz = np.array([[ 0,XYZ[2],-XYZ[1]], [-XYZ[2],0,XYZ[0]], [XYZ[1],-XYZ[0],0]] )
    Umat = Tmat+np.inner(Axyz,Smat)+np.inner(Smat.T,Axyz.T)+np.inner(np.inner(Axyz,Lmat),Axyz.T)
    beta = np.inner(np.inner(g,Umat),g)
    return G2lat.UijtoU6(beta)*gvec    
        
def AtomTLS2UIJ(atomData,atPtrs,Amat,rbObj):    #not used anywhere, but could be?
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    cx,ct,cs,cia = atPtrs
    TLStype,TLS = rbObj['ThermalMotion'][:2]
    Tmat = np.zeros((3,3))
    Lmat = np.zeros((3,3))
    Smat = np.zeros((3,3))
    G,g = G2lat.A2Gmat(Amat)
    gvec = 1./np.sqrt(np.array([g[0][0],g[1][1],g[2][2],g[0][1],g[0][2],g[1][2]]))
    if 'T' in TLStype:
        Tmat = G2lat.U6toUij(TLS[:6])
    if 'L' in TLStype:
        Lmat = G2lat.U6toUij(TLS[6:12])
    if 'S' in TLStype:
        Smat = np.array([ [TLS[18],TLS[12],TLS[13]], [TLS[14],TLS[19],TLS[15]], [TLS[16],TLS[17],0] ])
    for atom in atomData:
        XYZ = np.inner(Amat,atom[cx:cx+3])
        Axyz = np.array([ 0,XYZ[2],-XYZ[1], -XYZ[2],0,XYZ[0], XYZ[1],-XYZ[0],0],ndmin=2 )
        if 'U' in TLStype:
            atom[cia+1] = TLS[0]
            atom[cia] = 'I'
        else:
            atom[cia] = 'A'
            Umat = Tmat+np.inner(Axyz,Smat)+np.inner(Smat.T,Axyz.T)+np.inner(np.inner(Axyz,Lmat),Axyz.T)
            beta = np.inner(np.inner(g,Umat),g)
            atom[cia+2:cia+8] = G2spc.U2Uij(beta/gvec)

def GetXYZDist(xyz,XYZ,Amat):
    '''gets distance from position xyz to all XYZ, xyz & XYZ are np.array 
        and are in crystal coordinates; Amat is crystal to Cart matrix
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    return np.sqrt(np.sum(np.inner(Amat,XYZ-xyz)**2,axis=0))

def getAtomXYZ(atoms,cx):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    XYZ = []
    for atom in atoms:
        XYZ.append(atom[cx:cx+3])
    return np.array(XYZ)

def getRBTransMat(X,Y):
    '''Get transformation for Cartesian axes given 2 vectors
    X will  be parallel to new X-axis; X cross Y will be new Z-axis & 
    (X cross Y) cross Y will be new Y-axis
    Useful for rigid body axes definintion
    
    :param array X: normalized vector
    :param array Y: normalized vector
    
    :returns: array M: transformation matrix
    
    use as XYZ' = np.inner(M,XYZ) where XYZ are Cartesian
    
    '''
    Mat2 = np.cross(X,Y)      #UxV-->Z
    Mat2 /= np.sqrt(np.sum(Mat2**2))
    Mat3 = np.cross(Mat2,X)        #(UxV)xU-->Y
    Mat3 /= np.sqrt(np.sum(Mat3**2))
    return np.array([X,Mat3,Mat2])        
                
def RotateRBXYZ(Bmat,Cart,oriQ):
    '''rotate & transform cartesian coordinates to crystallographic ones
    no translation applied. To be used for numerical derivatives 
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    ''' returns crystal coordinates for atoms described by RBObj
    '''
    XYZ = np.zeros_like(Cart)
    for i,xyz in enumerate(Cart):
        XYZ[i] = np.inner(Bmat,prodQVQ(oriQ,xyz))
    return XYZ

def UpdateRBXYZ(Bmat,RBObj,RBData,RBType):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    ''' returns crystal coordinates for atoms described by RBObj
    '''
    RBRes = RBData[RBType][RBObj['RBId']]
    if RBType == 'Vector':
        vecs = RBRes['rbVect']
        mags = RBRes['VectMag']
        Cart = np.zeros_like(vecs[0])
        for vec,mag in zip(vecs,mags):
            Cart += vec*mag
    elif RBType == 'Residue':
        Cart = np.array(RBRes['rbXYZ'])
        for tor,seq in zip(RBObj['Torsions'],RBRes['rbSeq']):
            QuatA = AVdeg2Q(tor[0],Cart[seq[0]]-Cart[seq[1]])
            Cart[seq[3]] = prodQVQ(QuatA,(Cart[seq[3]]-Cart[seq[1]]))+Cart[seq[1]]
    XYZ = np.zeros_like(Cart)
    for i,xyz in enumerate(Cart):
        XYZ[i] = np.inner(Bmat,prodQVQ(RBObj['Orient'][0],xyz))+RBObj['Orig'][0]
    return XYZ,Cart

def UpdateMCSAxyz(Bmat,MCSA):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    xyz = []
    atTypes = []
    iatm = 0
    for model in MCSA['Models'][1:]:        #skip the MD model
        if model['Type'] == 'Atom':
            xyz.append(model['Pos'][0])
            atTypes.append(model['atType'])
            iatm += 1
        else:
            RBRes = MCSA['rbData'][model['Type']][model['RBId']]
            Pos = np.array(model['Pos'][0])
            Ori = np.array(model['Ori'][0])
            Qori = AVdeg2Q(Ori[0],Ori[1:])
            if model['Type'] == 'Vector':
                vecs = RBRes['rbVect']
                mags = RBRes['VectMag']
                Cart = np.zeros_like(vecs[0])
                for vec,mag in zip(vecs,mags):
                    Cart += vec*mag
            elif model['Type'] == 'Residue':
                Cart = np.array(RBRes['rbXYZ'])
                for itor,seq in enumerate(RBRes['rbSeq']):
                    QuatA = AVdeg2Q(model['Tor'][0][itor],Cart[seq[0]]-Cart[seq[1]])
                    Cart[seq[3]] = prodQVQ(QuatA,(Cart[seq[3]]-Cart[seq[1]]))+Cart[seq[1]]
            if model['MolCent'][1]:
                Cart -= model['MolCent'][0]
            for i,x in enumerate(Cart):
                xyz.append(np.inner(Bmat,prodQVQ(Qori,x))+Pos)
                atType = RBRes['rbTypes'][i]
                atTypes.append(atType)
                iatm += 1
    return np.array(xyz),atTypes
    
def SetMolCent(model,RBData):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    rideList = []
    RBRes = RBData[model['Type']][model['RBId']]
    if model['Type'] == 'Vector':
        vecs = RBRes['rbVect']
        mags = RBRes['VectMag']
        Cart = np.zeros_like(vecs[0])
        for vec,mag in zip(vecs,mags):
            Cart += vec*mag
    elif model['Type'] == 'Residue':
        Cart = np.array(RBRes['rbXYZ'])
        for seq in RBRes['rbSeq']:
            rideList += seq[3]
    centList = set(range(len(Cart)))-set(rideList)
    cent = np.zeros(3)
    for i in centList:
        cent += Cart[i]
    model['MolCent'][0] = cent/len(centList)    
    
def UpdateRBUIJ(Bmat,Cart,RBObj):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    ''' returns atom I/A, Uiso or UIJ for atoms at XYZ as described by RBObj
    '''
    TLStype,TLS = RBObj['ThermalMotion'][:2]
    T = np.zeros(6)
    L = np.zeros(6)
    S = np.zeros(8)
    if 'T' in TLStype:
        T = TLS[:6]
    if 'L' in TLStype:
        L = np.array(TLS[6:12])*(np.pi/180.)**2
    if 'S' in TLStype:
        S = np.array(TLS[12:])*(np.pi/180.)
    g = nl.inv(np.inner(Bmat,Bmat))
    gvec = np.sqrt(np.array([g[0][0]**2,g[1][1]**2,g[2][2]**2,
        g[0][0]*g[1][1],g[0][0]*g[2][2],g[1][1]*g[2][2]]))
    Uout = []
    Q = RBObj['Orient'][0]
    for X in Cart:
        X = prodQVQ(Q,X)
        if 'U' in TLStype:
            Uout.append(['I',TLS[0],0,0,0,0,0,0])
        elif not 'N' in TLStype:
            U = [0,0,0,0,0,0]
            U[0] = T[0]+L[1]*X[2]**2+L[2]*X[1]**2-2.0*L[5]*X[1]*X[2]+2.0*(S[2]*X[2]-S[4]*X[1])
            U[1] = T[1]+L[0]*X[2]**2+L[2]*X[0]**2-2.0*L[4]*X[0]*X[2]+2.0*(S[5]*X[0]-S[0]*X[2])
            U[2] = T[2]+L[1]*X[0]**2+L[0]*X[1]**2-2.0*L[3]*X[1]*X[0]+2.0*(S[1]*X[1]-S[3]*X[0])
            U[3] = T[3]+L[4]*X[1]*X[2]+L[5]*X[0]*X[2]-L[3]*X[2]**2-L[2]*X[0]*X[1]+  \
                S[4]*X[0]-S[5]*X[1]-(S[6]+S[7])*X[2]
            U[4] = T[4]+L[3]*X[1]*X[2]+L[5]*X[0]*X[1]-L[4]*X[1]**2-L[1]*X[0]*X[2]+  \
                S[3]*X[2]-S[2]*X[0]+S[6]*X[1]
            U[5] = T[5]+L[3]*X[0]*X[2]+L[4]*X[0]*X[1]-L[5]*X[0]**2-L[0]*X[2]*X[1]+  \
                S[0]*X[1]-S[1]*X[2]+S[7]*X[0]
            Umat = G2lat.U6toUij(U)
            beta = np.inner(np.inner(Bmat.T,Umat),Bmat)
            Uout.append(['A',0.0,]+list(G2lat.UijtoU6(beta)*gvec))
        else:
            Uout.append(['N',])
    return Uout
    
def GetSHCoeff(pId,parmDict,SHkeys):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    SHCoeff = {}
    for shkey in SHkeys:
        shname = str(pId)+'::'+shkey
        SHCoeff[shkey] = parmDict[shname]
    return SHCoeff
        
def getMass(generalData):
    '''Computes mass of unit cell contents
    
    :param dict generalData: The General dictionary in Phase
    
    :returns: float mass: Crystal unit cell mass in AMU.
    
    '''
    mass = 0.
    for i,elem in enumerate(generalData['AtomTypes']):
        mass += generalData['NoAtoms'][elem]*generalData['AtomMass'][i]
    return max(mass,1.0)    

def getDensity(generalData):
    '''calculate crystal structure density
    
    :param dict generalData: The General dictionary in Phase
    
    :returns: float density: crystal density in gm/cm^3
    
    '''
    mass = getMass(generalData)
    Volume = generalData['Cell'][7]
    density = mass/(0.6022137*Volume)
    return density,Volume/mass
    
def getWave(Parms):
    '''returns wavelength from Instrument parameters dictionary
    
    :param dict Parms: Instrument parameters;
        must contain:
        Lam: single wavelength
        or
        Lam1: Ka1 radiation wavelength
    
    :returns: float wave: wavelength
    
    '''
    try:
        return Parms['Lam'][1]
    except KeyError:
        return Parms['Lam1'][1]
        
def getMeanWave(Parms):
    '''returns mean wavelength from Instrument parameters dictionary
    
    :param dict Parms: Instrument parameters;
        must contain:
        Lam: single wavelength
        or
        Lam1,Lam2: Ka1,Ka2 radiation wavelength
        I(L2)/I(L1): Ka2/Ka1 ratio
    
    :returns: float wave: mean wavelength
    
    '''
    try:
        return Parms['Lam'][1]
    except KeyError:
        meanLam = (Parms['Lam1'][1]+Parms['I(L2)/I(L1)'][1]*Parms['Lam2'][1])/   \
            (1.+Parms['I(L2)/I(L1)'][1])
        return meanLam
    
        
def El2Mass(Elements):
    '''compute molecular weight from Elements 
    
    :param dict Elements: elements in molecular formula; 
        each must contain 
        Num: number of atoms in formula
        Mass: at. wt. 
    
    :returns: float mass: molecular weight.
    
    '''
    mass = 0
    for El in Elements:
        mass += Elements[El]['Num']*Elements[El]['Mass']
    return mass
        
def Den2Vol(Elements,density):
    '''converts density to molecular volume
    
    :param dict Elements: elements in molecular formula; 
        each must contain 
        Num: number of atoms in formula
        Mass: at. wt. 
    :param float density: material density in gm/cm^3
    
    :returns: float volume: molecular volume in A^3 
    
    '''
    return El2Mass(Elements)/(density*0.6022137)
    
def Vol2Den(Elements,volume):
    '''converts volume to density
    
    :param dict Elements: elements in molecular formula; 
        each must contain 
        Num: number of atoms in formula
        Mass: at. wt. 
    :param float volume: molecular volume in A^3
    
    :returns: float density: material density in gm/cm^3
    
    '''
    return El2Mass(Elements)/(volume*0.6022137)
    
def El2EstVol(Elements):
    '''Estimate volume from molecular formula; assumes atom volume = 10A^3
    
    :param dict Elements: elements in molecular formula; 
        each must contain 
        Num: number of atoms in formula
    
    :returns: float volume: estimate of molecular volume in A^3
    
    '''
    vol = 0
    for El in Elements:
        vol += 10.*Elements[El]['Num']
    return vol
    
def XScattDen(Elements,vol,wave=0.):
    '''Estimate X-ray scattering density from molecular formula & volume;
    ignores valence, but includes anomalous effects
    
    :param dict Elements: elements in molecular formula; 
        each element must contain 
        Num: number of atoms in formula
        Z: atomic number
    :param float vol: molecular volume in A^3
    :param float wave: optional wavelength in A
    
    :returns: float rho: scattering density in 10^10cm^-2; 
        if wave > 0 the includes f' contribution
    :returns: float mu: if wave>0 absorption coeff in cm^-1 ; otherwise 0
    :returns: float fpp: if wave>0 f" in 10^10cm^-2; otherwise 0
    
    '''
    rho = 0
    mu = 0
    fpp = 0
    if wave: 
        Xanom = XAnomAbs(Elements,wave)
    for El in Elements:
        f0 = Elements[El]['Z']
        if wave:
            f0 += Xanom[El][0]
            fpp += Xanom[El][1]*Elements[El]['Num']
            mu += Xanom[El][2]*Elements[El]['Num']
        rho += Elements[El]['Num']*f0
    return 28.179*rho/vol,0.1*mu/vol,28.179*fpp/vol
    
def NCScattDen(Elements,vol,wave=0.):
    '''Estimate neutron scattering density from molecular formula & volume;
    ignores valence, but includes anomalous effects
    
    :param dict Elements: elements in molecular formula; 
        each element must contain 
        Num: number of atoms in formula
        Z: atomic number
    :param float vol: molecular volume in A^3
    :param float wave: optional wavelength in A
    
    :returns: float rho: scattering density in 10^10cm^-2; 
        if wave > 0 the includes f' contribution
    :returns: float mu: if wave>0 absorption coeff in cm^-1 ; otherwise 0
    :returns: float fpp: if wave>0 f" in 10^10cm^-2; otherwise 0
    
    '''
    rho = 0
    mu = 0
    bpp = 0
    for El in Elements:
        isotope = Elements[El]['Isotope']
        b0 = Elements[El]['Isotopes'][isotope]['SL'][0]
        mu += Elements[El]['Isotopes'][isotope].get('SA',0.)*Elements[El]['Num']
        if wave and 'BW-LS' in Elements[El]['Isotopes'][isotope]:
            Re,Im,E0,gam,A,E1,B,E2 = Elements[El]['Isotopes'][isotope]['BW-LS'][1:]
            Emev = 81.80703/wave**2
            T0 = Emev-E0
            T1 = Emev-E1
            T2 = Emev-E2
            D0 = T0**2+gam**2
            D1 = T1**2+gam**2
            D2 = T2**2+gam**2
            b0 += Re*(T0/D0+A*T1/D1+B*T2/D2)
            bpp += Im*(1/D0+A/D1+B/D2)
        else:
            bpp += Elements[El]['Isotopes'][isotope]['SL'][1]
        rho += Elements[El]['Num']*b0
    if wave: mu *= wave
    return 100.*rho/vol,mu/vol,100.*bpp/vol
    
def wavekE(wavekE):
    '''Convert wavelength to energy & vise versa
    
    :param float waveKe:wavelength in A or energy in kE
    
    :returns float waveKe:the other one
    
    '''
    return 12.397639/wavekE
        
def XAnomAbs(Elements,wave):
    kE = wavekE(wave)
    Xanom = {}
    for El in Elements:
        Orbs = G2el.GetXsectionCoeff(El)
        Xanom[El] = G2el.FPcalc(Orbs, kE)
    return Xanom        #f',f", mu
    
################################################################################
#### Modulation math
################################################################################

def makeWaves(waveTypes,FSSdata,XSSdata,USSdata,MSSdata,Mast):
    '''
    waveTypes: array nAtoms: 'Fourier','ZigZag' or 'Block'
    FSSdata: array 2 x atoms x waves    (sin,cos terms)
    XSSdata: array 2x3 x atoms X waves (sin,cos terms)
    USSdata: array 2x6 x atoms X waves (sin,cos terms)
    MSSdata: array 2x3 x atoms X waves (sin,cos terms)
    
    Mast: array orthogonalization matrix for Uij
    '''
    ngl = 36                    #selected for integer steps for 1/6,1/4,1/3...
    glTau,glWt = pwd.pygauleg(0.,1.,ngl)         #get Gauss-Legendre intervals & weights
    mglTau = np.arange(0.,1.,1./ngl)
    Ax = np.array(XSSdata[:3]).T   #atoms x waves x sin pos mods
    Bx = np.array(XSSdata[3:]).T   #...cos pos mods
    Af = np.array(FSSdata[0]).T    #sin frac mods x waves x atoms
    Bf = np.array(FSSdata[1]).T    #cos frac mods...
    Au = Mast*np.array(G2lat.U6toUij(USSdata[:6])).T   #atoms x waves x sin Uij mods as betaij
    Bu = Mast*np.array(G2lat.U6toUij(USSdata[6:])).T   #...cos Uij mods as betaij
    Am = np.array(MSSdata[:3]).T   #atoms x waves x sin pos mods
    Bm = np.array(MSSdata[3:]).T   #...cos pos mods
    nWaves = [Af.shape[1],Ax.shape[1],Au.shape[1],Am.shape[1]] 
    if nWaves[0]:
        tauF = np.arange(1.,nWaves[0]+1)[:,nxs]*glTau  #Fwaves x ngl
        FmodA = Af[:,:,nxs]*np.sin(twopi*tauF[nxs,:,:])   #atoms X Fwaves X ngl
        FmodB = Bf[:,:,nxs]*np.cos(twopi*tauF[nxs,:,:])
        Fmod = np.sum(1.0+FmodA+FmodB,axis=1)             #atoms X ngl; sum waves
    else:
        Fmod = 1.0           
    XmodZ = np.zeros((Ax.shape[0],Ax.shape[1],3,ngl))
    XmodA = np.zeros((Ax.shape[0],Ax.shape[1],3,ngl))
    XmodB = np.zeros((Ax.shape[0],Ax.shape[1],3,ngl))
    for iatm in range(Ax.shape[0]):
        nx = 0
        if 'ZigZag' in waveTypes[iatm]:
            nx = 1
            Tmm = Ax[iatm][0][:2]                        
            XYZmax = np.array([Ax[iatm][0][2],Bx[iatm][0][0],Bx[iatm][0][1]])
            XmodZ[iatm][0] += posZigZag(glTau,Tmm,XYZmax).T
        elif 'Block' in waveTypes[iatm]:
            nx = 1
            Tmm = Ax[iatm][0][:2]                        
            XYZmax = np.array([Ax[iatm][0][2],Bx[iatm][0][0],Bx[iatm][0][1]])
            XmodZ[iatm][0] += posBlock(glTau,Tmm,XYZmax).T
        tauX = np.arange(1.,nWaves[1]+1-nx)[:,nxs]*glTau  #Xwaves x ngl
        if nx:    
            XmodA[iatm][:-nx] = Ax[iatm,nx:,:,nxs]*np.sin(twopi*tauX[nxs,:,nxs,:]) #atoms X waves X 3 X ngl
            XmodB[iatm][:-nx] = Bx[iatm,nx:,:,nxs]*np.cos(twopi*tauX[nxs,:,nxs,:]) #ditto
        else:
            XmodA[iatm] = Ax[iatm,:,:,nxs]*np.sin(twopi*tauX[nxs,:,nxs,:]) #atoms X waves X 3 X ngl
            XmodB[iatm] = Bx[iatm,:,:,nxs]*np.cos(twopi*tauX[nxs,:,nxs,:]) #ditto
    Xmod = np.sum(XmodA+XmodB+XmodZ,axis=1)                #atoms X 3 X ngl; sum waves
    Xmod = np.swapaxes(Xmod,1,2)
    if nWaves[2]:
        tauU = np.arange(1.,nWaves[2]+1)[:,nxs]*glTau     #Uwaves x ngl
        UmodA = Au[:,:,:,:,nxs]*np.sin(twopi*tauU[nxs,:,nxs,nxs,:]) #atoms x waves x 3x3 x ngl
        UmodB = Bu[:,:,:,:,nxs]*np.cos(twopi*tauU[nxs,:,nxs,nxs,:]) #ditto
        Umod = np.swapaxes(np.sum(UmodA+UmodB,axis=1),1,3)      #atoms x 3x3 x ngl; sum waves
    else:
        Umod = 1.0
    if nWaves[3]:
        tauM = np.arange(1.,nWaves[3]+1-nx)[:,nxs]*mglTau  #Mwaves x ngl
        MmodA = Am[:,:,:,nxs]*np.sin(twopi*tauM[nxs,:,nxs,:]) #atoms X waves X 3 X ngl
        MmodB = Bm[:,:,:,nxs]*np.cos(twopi*tauM[nxs,:,nxs,:]) #ditto
        Mmod = np.sum(MmodA+MmodB,axis=1)
        Mmod = np.swapaxes(Mmod,1,2)    #Mxyz,Ntau,Natm
    else:
        Mmod = 1.0
    return ngl,nWaves,Fmod,Xmod,Umod,Mmod,glTau,glWt

def MagMod(glTau,XYZ,modQ,MSSdata,SGData,SSGData):
    '''
    this needs to make magnetic moment modulations & magnitudes as 
    fxn of gTau points
    '''
    Am = np.array(MSSdata[3:]).T   #atoms x waves x cos pos mods
    Bm = np.array(MSSdata[:3]).T  #...sin pos mods
    nWaves = Am.shape[1]
    SGMT = np.array([ops[0] for ops in SGData['SGOps']])        #not .T!!
    Sinv = np.array([nl.inv(ops[0]) for ops in SSGData['SSGOps']])
    SGT = np.array([ops[1] for ops in SSGData['SSGOps']])
    if SGData['SGInv']:
        SGMT = np.vstack((SGMT,-SGMT))
        Sinv =np.vstack((Sinv,-Sinv))
        SGT = np.vstack((SGT,-SGT))
    SGMT = np.vstack([SGMT for cen in SGData['SGCen']])
    Sinv = np.vstack([Sinv for cen in SGData['SGCen']])
    SGT = np.vstack([SGT+cen for cen in SSGData['SSGCen']])%1.
    if SGData['SGGray']:
        SGMT = np.vstack((SGMT,SGMT))
        Sinv =np.vstack((Sinv,Sinv))
        SGT = np.vstack((SGT,SGT+.5))%1.
    mst = Sinv[:,3,:3]
    epsinv = Sinv[:,3,3]
    phi = np.inner(XYZ,modQ).T
    TA = np.sum(mst[nxs,:,:]*(XYZ-SGT[:,:3][nxs,:,:]),axis=-1).T
    tauT =  TA[nxs,:,:] + epsinv[nxs,:,nxs]*(glTau[:,nxs,nxs]-SGT[:,3][nxs,:,nxs]+phi[nxs,:,:])
    modind = np.arange(nWaves)+1.
    phase = (modind[:,nxs,nxs]*tauT)     #Nops,Natm,Nwave
    psin = np.sin(twopi*phase)
    pcos = np.cos(twopi*phase)
    MmodA = np.sum(Am[nxs,nxs,:,:,:]*pcos[:,:,:,nxs,nxs],axis=3)/2.    #cos term
    MmodB = np.sum(Bm[nxs,nxs,:,:,:]*psin[:,:,:,nxs,nxs],axis=3)/2.    #sin term
    MmodA = np.sum(SGMT[nxs,:,nxs,:,:]*MmodA[:,:,:,nxs,:],axis=-1)*SGData['MagMom'][nxs,:,nxs,nxs]
    MmodB = np.sum(SGMT[nxs,:,nxs,:,:]*MmodB[:,:,:,nxs,:],axis=-1)*SGData['MagMom'][nxs,:,nxs,nxs]
    return MmodA,MmodB    #Ntau,Nops,Natm,,Mxyz; cos & sin parts; sum matches drawn atom moments
        
def Modulation(H,HP,nWaves,Fmod,Xmod,Umod,glTau,glWt):
    '''
    H: array nRefBlk x ops X hklt
    HP: array nRefBlk x ops X hklt proj to hkl
    nWaves: list number of waves for frac, pos, uij & mag
    Fmod: array 2 x atoms x waves    (sin,cos terms)
    Xmod: array atoms X 3 X ngl
    Umod: array atoms x 3x3 x ngl
    glTau,glWt: arrays Gauss-Lorentzian pos & wts
    '''
    
    if nWaves[2]:       #uij (adp) waves
        if len(HP.shape) > 2:
            HbH = np.exp(-np.sum(HP[:,:,nxs,nxs,:]*np.inner(HP,Umod),axis=-1)) # refBlk x ops x atoms x ngl add Overhauser corr.?
        else:
            HbH = np.exp(-np.sum(HP[:,nxs,nxs,:]*np.inner(HP,Umod),axis=-1)) # refBlk x ops x atoms x ngl add Overhauser corr.?
    else:
        HbH = 1.0
    HdotX = np.inner(HP,Xmod)                   #refBlk x ops x atoms X ngl
    if len(H.shape) > 2:
        D = H[:,:,3:]*glTau[nxs,nxs,:]              #m*e*tau; refBlk x ops X ngl
        HdotXD = twopi*(HdotX+D[:,:,nxs,:])
    else:
        D = H[:,3:]*glTau[nxs,:]              #m*e*tau; refBlk x ops X ngl
        HdotXD = twopi*(HdotX+D[:,nxs,:])
    cosHA = np.sum(Fmod*HbH*np.cos(HdotXD)*glWt,axis=-1)       #real part; refBlk X ops x atoms; sum for G-L integration
    sinHA = np.sum(Fmod*HbH*np.sin(HdotXD)*glWt,axis=-1)       #imag part; ditto
    return np.array([cosHA,sinHA])             # 2 x refBlk x SGops x atoms
    
#def MagModulation(H,HP,nWaves,Fmod,Xmod,Umod,Mmod,glTau,glWt):
#    '''
#    H: array nRefBlk x ops X hklt
#    HP: array nRefBlk x ops X hklt proj to hkl
#    nWaves: list number of waves for frac, pos, uij & mag
#    Fmod: array 2 x atoms x waves    (sin,cos terms)
#    Xmod: array atoms X 3 X ngl
#    Umod: array atoms x 3x3 x ngl
#    Mmod: array atoms x 3x3 x ngl
#    glTau,glWt: arrays Gauss-Lorentzian pos & wts
#    '''
#    
#    if nWaves[2]:       #uij (adp) waves
#        if len(HP.shape) > 2:
#            HbH = np.exp(-np.sum(HP[:,:,nxs,nxs,:]*np.inner(HP,Umod),axis=-1)) # refBlk x ops x atoms x ngl add Overhauser corr.?
#        else:
#            HbH = np.exp(-np.sum(HP[:,nxs,nxs,:]*np.inner(HP,Umod),axis=-1)) # refBlk x ops x atoms x ngl add Overhauser corr.?
#    else:
#        HbH = 1.0
#    HdotX = np.inner(HP,Xmod)                   #refBlk x ops x atoms X ngl
#    if len(H.shape) > 2:
#        D = H[:,:,3:]*glTau[nxs,nxs,:]              #m*e*tau; refBlk x ops X ngl
#        HdotXD = twopi*(HdotX+D[:,:,nxs,:])
#    else:
#        D = H[:,3:]*glTau[nxs,:]              #m*e*tau; refBlk x ops X ngl
#        HdotXD = twopi*(HdotX+D[:,nxs,:])
#    M = np.swapaxes(Mmod,1,2)
#    cosHA = np.sum(M[nxs,nxs,:,:,:]*(Fmod*HbH*np.cos(HdotXD)[:,:,:,nxs,:]*glWt),axis=-1)       #real part; refBlk X ops x atoms; sum for G-L integration
#    sinHA = np.sum(M[nxs,nxs,:,:,:]*(Fmod*HbH*np.sin(HdotXD)[:,:,:,nxs,:]*glWt),axis=-1)       #imag part; ditto
#    return np.array([cosHA,sinHA])             # 2 x refBlk x SGops x atoms
#
def ModulationTw(H,HP,nWaves,Fmod,Xmod,Umod,glTau,glWt):
    '''
    H: array nRefBlk x tw x ops X hklt
    HP: array nRefBlk x tw x ops X hklt proj to hkl
    Fmod: array 2 x atoms x waves    (sin,cos terms)
    Xmod: array atoms X ngl X 3
    Umod: array atoms x ngl x 3x3
    glTau,glWt: arrays Gauss-Lorentzian pos & wts
    '''
    
    if nWaves[2]:
        if len(HP.shape) > 3:   #Blocks of reflections
            HbH = np.exp(-np.sum(HP[:,:,nxs,nxs,:]*np.inner(HP,Umod),axis=-1)) # refBlk x ops x atoms x ngl add Overhauser corr.?
        else:   #single reflections
            HbH = np.exp(-np.sum(HP[:,nxs,nxs,:]*np.inner(HP,Umod),axis=-1)) # refBlk x ops x atoms x ngl add Overhauser corr.?
    else:
        HbH = 1.0
    HdotX = np.inner(HP,Xmod)                   #refBlk x tw x ops x atoms X ngl
    if len(H.shape) > 3:
        D = glTau*H[:,:,:,3:,nxs]              #m*e*tau; refBlk x tw x ops X ngl
        HdotXD = twopi*(HdotX+D[:,:,:,nxs,:])
    else:
        D = H*glTau[nxs,:]              #m*e*tau; refBlk x ops X ngl
        HdotXD = twopi*(HdotX+D[:,nxs,:])
    cosHA = np.sum(Fmod*HbH*np.cos(HdotXD)*glWt,axis=-1)       #real part; refBlk X ops x atoms; sum for G-L integration
    sinHA = np.sum(Fmod*HbH*np.sin(HdotXD)*glWt,axis=-1)       #imag part; ditto
    return np.array([cosHA,sinHA])             # 2 x refBlk x SGops x atoms
    
def makeWavesDerv(ngl,waveTypes,FSSdata,XSSdata,USSdata,Mast):
    '''
    Only for Fourier waves for fraction, position & adp (probably not used for magnetism)
    FSSdata: array 2 x atoms x waves    (sin,cos terms)
    XSSdata: array 2x3 x atoms X waves (sin,cos terms)
    USSdata: array 2x6 x atoms X waves (sin,cos terms)
    Mast: array orthogonalization matrix for Uij
    '''
    glTau,glWt = pwd.pygauleg(0.,1.,ngl)         #get Gauss-Legendre intervals & weights
    waveShapes = [FSSdata.T.shape,XSSdata.T.shape,USSdata.T.shape]
    Af = np.array(FSSdata[0]).T    #sin frac mods x waves x atoms
    Bf = np.array(FSSdata[1]).T    #cos frac mods...
    Ax = np.array(XSSdata[:3]).T   #...cos pos mods x waves x atoms
    Bx = np.array(XSSdata[3:]).T   #...cos pos mods
    Au = Mast*np.array(G2lat.U6toUij(USSdata[:6])).T   #atoms x waves x sin Uij mods
    Bu = Mast*np.array(G2lat.U6toUij(USSdata[6:])).T   #...cos Uij mods
    nWaves = [Af.shape[1],Ax.shape[1],Au.shape[1]] 
    StauX = np.zeros((Ax.shape[0],Ax.shape[1],3,ngl))    #atoms x waves x 3 x ngl
    CtauX = np.zeros((Ax.shape[0],Ax.shape[1],3,ngl))
    ZtauXt = np.zeros((Ax.shape[0],2,3,ngl))               #atoms x Tminmax x 3 x ngl
    ZtauXx = np.zeros((Ax.shape[0],3,ngl))               #atoms x XYZmax x ngl
    for iatm in range(Ax.shape[0]):
        nx = 0
        if 'ZigZag' in waveTypes[iatm]:
            nx = 1
        elif 'Block' in waveTypes[iatm]:
            nx = 1
        tauX = np.arange(1.,nWaves[1]+1-nx)[:,nxs]*glTau  #Xwaves x ngl
        if nx:    
            StauX[iatm][nx:] = np.ones_like(Ax)[iatm,nx:,:,nxs]*np.sin(twopi*tauX)[nxs,:,nxs,:]   #atoms X waves X 3(xyz) X ngl
            CtauX[iatm][nx:] = np.ones_like(Bx)[iatm,nx:,:,nxs]*np.cos(twopi*tauX)[nxs,:,nxs,:]   #ditto
        else:
            StauX[iatm] = np.ones_like(Ax)[iatm,:,:,nxs]*np.sin(twopi*tauX)[nxs,:,nxs,:]   #atoms X waves X 3(xyz) X ngl
            CtauX[iatm] = np.ones_like(Bx)[iatm,:,:,nxs]*np.cos(twopi*tauX)[nxs,:,nxs,:]   #ditto
    if nWaves[0]:
        tauF = np.arange(1.,nWaves[0]+1)[:,nxs]*glTau  #Fwaves x ngl
        StauF = np.ones_like(Af)[:,:,nxs]*np.sin(twopi*tauF)[nxs,:,:] #also dFmod/dAf
        CtauF = np.ones_like(Bf)[:,:,nxs]*np.cos(twopi*tauF)[nxs,:,:] #also dFmod/dBf
    else:
        StauF = 1.0
        CtauF = 1.0
    if nWaves[2]:
        tauU = np.arange(1.,nWaves[2]+1)[:,nxs]*glTau     #Uwaves x ngl
        StauU = np.ones_like(Au)[:,:,:,:,nxs]*np.sin(twopi*tauU)[nxs,:,nxs,nxs,:]   #also dUmodA/dAu
        CtauU = np.ones_like(Bu)[:,:,:,:,nxs]*np.cos(twopi*tauU)[nxs,:,nxs,nxs,:]   #also dUmodB/dBu
        UmodA = Au[:,:,:,:,nxs]*StauU #atoms x waves x 3x3 x ngl
        UmodB = Bu[:,:,:,:,nxs]*CtauU #ditto
#derivs need to be ops x atoms x waves x 6uij; ops x atoms x waves x ngl x 6uij before sum
        StauU = np.rollaxis(np.rollaxis(np.swapaxes(StauU,2,4),-1),-1)
        CtauU = np.rollaxis(np.rollaxis(np.swapaxes(CtauU,2,4),-1),-1)
    else:
        StauU = 1.0
        CtauU = 1.0
        UmodA = 0.
        UmodB = 0.
    return waveShapes,[StauF,CtauF],[StauX,CtauX,ZtauXt,ZtauXx],[StauU,CtauU],UmodA+UmodB
    
def ModulationDerv(H,HP,Hij,nWaves,waveShapes,Fmod,Xmod,UmodAB,SCtauF,SCtauX,SCtauU,glTau,glWt):
    '''
    Compute Fourier modulation derivatives
    H: array ops X hklt proj to hkl
    HP: array ops X hklt proj to hkl
    Hij: array 2pi^2[a*^2h^2 b*^2k^2 c*^2l^2 a*b*hk a*c*hl b*c*kl] of projected hklm to hkl space
    '''
   
    Mf = [H.shape[0],]+list(waveShapes[0])    #=[ops,atoms,waves,2] (sin+cos frac mods)
    dGdMfC = np.zeros(Mf)
    dGdMfS = np.zeros(Mf)
    Mx = [H.shape[0],]+list(waveShapes[1])   #=[ops,atoms,waves,6] (sin+cos pos mods)
    dGdMxC = np.zeros(Mx)
    dGdMxS = np.zeros(Mx)
    Mu = [H.shape[0],]+list(waveShapes[2])    #=[ops,atoms,waves,12] (sin+cos Uij mods)
    dGdMuC = np.zeros(Mu)
    dGdMuS = np.zeros(Mu)
    
    D = twopi*H[:,3][:,nxs]*glTau[nxs,:]              #m*e*tau; ops X ngl
    HdotX = twopi*np.inner(HP,Xmod)        #ops x atoms X ngl
    HdotXD = HdotX+D[:,nxs,:]
    if nWaves[2]:
        Umod = np.swapaxes((UmodAB),2,4)      #atoms x waves x ngl x 3x3 (symmetric so I can do this!) 
        HuH = np.sum(HP[:,nxs,nxs,nxs]*np.inner(HP,Umod),axis=-1)    #ops x atoms x waves x ngl
        HuH = np.sum(HP[:,nxs,nxs,nxs]*np.inner(HP,Umod),axis=-1)    #ops x atoms x waves x ngl
        HbH = np.exp(-np.sum(HuH,axis=-2)) # ops x atoms x ngl; sum waves - OK vs Modulation version
#        part1 = -np.exp(-HuH)*Fmod[nxs,:,nxs,:]    #ops x atoms x waves x ngl
        part1 = -np.exp(-HuH)*Fmod    #ops x atoms x waves x ngl
        dUdAu = Hij[:,nxs,nxs,nxs,:]*np.rollaxis(G2lat.UijtoU6(SCtauU[0]),0,4)[nxs,:,:,:,:]    #ops x atoms x waves x ngl x 6sinUij
        dUdBu = Hij[:,nxs,nxs,nxs,:]*np.rollaxis(G2lat.UijtoU6(SCtauU[1]),0,4)[nxs,:,:,:,:]    #ops x atoms x waves x ngl x 6cosUij
        dGdMuCa = np.sum(part1[:,:,:,:,nxs]*dUdAu*np.cos(HdotXD)[:,:,nxs,:,nxs]*glWt[nxs,nxs,nxs,:,nxs],axis=-2)   #ops x atoms x waves x 6uij; G-L sum
        dGdMuCb = np.sum(part1[:,:,:,:,nxs]*dUdBu*np.cos(HdotXD)[:,:,nxs,:,nxs]*glWt[nxs,nxs,nxs,:,nxs],axis=-2)
        dGdMuC = np.concatenate((dGdMuCa,dGdMuCb),axis=-1)   #ops x atoms x waves x 12uij
        dGdMuSa = np.sum(part1[:,:,:,:,nxs]*dUdAu*np.sin(HdotXD)[:,:,nxs,:,nxs]*glWt[nxs,nxs,nxs,:,nxs],axis=-2)   #ops x atoms x waves x 6uij; G-L sum
        dGdMuSb = np.sum(part1[:,:,:,:,nxs]*dUdBu*np.sin(HdotXD)[:,:,nxs,:,nxs]*glWt[nxs,nxs,nxs,:,nxs],axis=-2)
        dGdMuS = np.concatenate((dGdMuSa,dGdMuSb),axis=-1)   #ops x atoms x waves x 12uij
    else:
        HbH = np.ones_like(HdotX)
    dHdXA = twopi*HP[:,nxs,nxs,nxs,:]*np.swapaxes(SCtauX[0],-1,-2)[nxs,:,:,:,:]    #ops x atoms x sine waves x ngl x xyz
    dHdXB = twopi*HP[:,nxs,nxs,nxs,:]*np.swapaxes(SCtauX[1],-1,-2)[nxs,:,:,:,:]    #ditto - cos waves
# ops x atoms x waves x 2xyz - real part - good
#    dGdMxCa = -np.sum((Fmod[nxs,:,:]*HbH)[:,:,nxs,:,nxs]*(dHdXA*np.sin(HdotXD)[:,:,nxs,:,nxs])*glWt[nxs,nxs,nxs,:,nxs],axis=-2)
#    dGdMxCb = -np.sum((Fmod[nxs,:,:]*HbH)[:,:,nxs,:,nxs]*(dHdXB*np.sin(HdotXD)[:,:,nxs,:,nxs])*glWt[nxs,nxs,nxs,:,nxs],axis=-2)
    dGdMxCa = -np.sum((Fmod*HbH)[:,:,nxs,:,nxs]*(dHdXA*np.sin(HdotXD)[:,:,nxs,:,nxs])*glWt[nxs,nxs,nxs,:,nxs],axis=-2)
    dGdMxCb = -np.sum((Fmod*HbH)[:,:,nxs,:,nxs]*(dHdXB*np.sin(HdotXD)[:,:,nxs,:,nxs])*glWt[nxs,nxs,nxs,:,nxs],axis=-2)
    dGdMxC = np.concatenate((dGdMxCa,dGdMxCb),axis=-1)
# ops x atoms x waves x 2xyz - imag part - good
#    dGdMxSa = np.sum((Fmod[nxs,:,:]*HbH)[:,:,nxs,:,nxs]*(dHdXA*np.cos(HdotXD)[:,:,nxs,:,nxs])*glWt[nxs,nxs,nxs,:,nxs],axis=-2)    
#    dGdMxSb = np.sum((Fmod[nxs,:,:]*HbH)[:,:,nxs,:,nxs]*(dHdXB*np.cos(HdotXD)[:,:,nxs,:,nxs])*glWt[nxs,nxs,nxs,:,nxs],axis=-2)    
    dGdMxSa = np.sum((Fmod*HbH)[:,:,nxs,:,nxs]*(dHdXA*np.cos(HdotXD)[:,:,nxs,:,nxs])*glWt[nxs,nxs,nxs,:,nxs],axis=-2)    
    dGdMxSb = np.sum((Fmod*HbH)[:,:,nxs,:,nxs]*(dHdXB*np.cos(HdotXD)[:,:,nxs,:,nxs])*glWt[nxs,nxs,nxs,:,nxs],axis=-2)    
    dGdMxS = np.concatenate((dGdMxSa,dGdMxSb),axis=-1)
    return [dGdMfC,dGdMfS],[dGdMxC,dGdMxS],[dGdMuC,dGdMuS]
        
def posFourier(tau,psin,pcos):
    A = np.array([ps[:,nxs]*np.sin(2*np.pi*(i+1)*tau) for i,ps in enumerate(psin)])
    B = np.array([pc[:,nxs]*np.cos(2*np.pi*(i+1)*tau) for i,pc in enumerate(pcos)])
    return np.sum(A,axis=0)+np.sum(B,axis=0)
    
def posZigZag(T,Tmm,Xmax):
    DT = Tmm[1]-Tmm[0]
    Su = 2.*Xmax/DT
    Sd = 2.*Xmax/(1.-DT)
    A = np.array([np.where(  0.< (t-Tmm[0])%1. <= DT, -Xmax+Su*((t-Tmm[0])%1.), Xmax-Sd*((t-Tmm[1])%1.)) for t in T])
    return A
    
#def posZigZagDerv(T,Tmm,Xmax):
#    DT = Tmm[1]-Tmm[0]
#    Su = 2.*Xmax/DT
#    Sd = 2.*Xmax/(1.-DT)
#    dAdT = np.zeros((2,3,len(T)))
#    dAdT[0] = np.array([np.where(Tmm[0] < t <= Tmm[1],Su*(t-Tmm[0]-1)/DT,-Sd*(t-Tmm[1])/(1.-DT)) for t in T]).T
#    dAdT[1] = np.array([np.where(Tmm[0] < t <= Tmm[1],-Su*(t-Tmm[0])/DT,Sd*(t-Tmm[1])/(1.-DT)) for t in T]).T
#    dAdX = np.ones(3)[:,nxs]*np.array([np.where(Tmm[0] < t%1. <= Tmm[1],-1.+2.*(t-Tmm[0])/DT,1.-2.*(t-Tmm[1])%1./DT) for t in T])
#    return dAdT,dAdX

def posBlock(T,Tmm,Xmax):
    A = np.array([np.where(Tmm[0] < t%1. <= Tmm[1],-Xmax,Xmax) for t in T])
    return A
    
#def posBlockDerv(T,Tmm,Xmax):
#    dAdT = np.zeros((2,3,len(T)))
#    ind = np.searchsorted(T,Tmm)
#    dAdT[0,:,ind[0]] = -Xmax/len(T)
#    dAdT[1,:,ind[1]] = Xmax/len(T)
#    dAdX = np.ones(3)[:,nxs]*np.array([np.where(Tmm[0] < t <= Tmm[1],-1.,1.) for t in T])  #OK
#    return dAdT,dAdX
    
def fracCrenel(tau,Toff,Twid):
    Tau = (tau-Toff)%1.
    A = np.where(Tau<Twid,1.,0.)
    return A
    
def fracFourier(tau,fsin,fcos):
    if len(fsin) == 1:
        A = np.array([fsin[0]*np.sin(2.*np.pi*tau)])
        B = np.array([fcos[0]*np.cos(2.*np.pi*tau)])
    else:
        A = np.array([fs[:,nxs]*np.sin(2.*np.pi*(i+1)*tau) for i,fs in enumerate(fsin)])
        B = np.array([fc[:,nxs]*np.cos(2.*np.pi*(i+1)*tau) for i,fc in enumerate(fcos)])
    return np.sum(A,axis=0)+np.sum(B,axis=0)

def ApplyModulation(data,tau):
    '''Applies modulation to drawing atom positions & Uijs for given tau
    '''
    generalData = data['General']
    cell = generalData['Cell'][1:7]
    G,g = G2lat.cell2Gmat(cell)
    SGData = generalData['SGData']
    SSGData = generalData['SSGData']
    cx,ct,cs,cia = generalData['AtomPtrs']
    drawingData = data['Drawing']
    modul = generalData['SuperVec'][0]
    dcx,dct,dcs,dci = drawingData['atomPtrs']
    atoms = data['Atoms']
    drawAtoms = drawingData['Atoms']
    Fade = np.ones(len(drawAtoms))
    for atom in atoms:
        atxyz = np.array(atom[cx:cx+3])
        atuij = np.array(atom[cia+2:cia+8])
        Sfrac = atom[-1]['SS1']['Sfrac']
        Spos = atom[-1]['SS1']['Spos']
        Sadp = atom[-1]['SS1']['Sadp']
        if generalData['Type'] == 'magnetic':
            Smag = atom[-1]['SS1']['Smag']
            atmom = np.array(atom[cx+4:cx+7])
        indx = FindAtomIndexByIDs(drawAtoms,dci,[atom[cia+8],],True)
        for ind in indx:
            drawatom = drawAtoms[ind]
            opr = drawatom[dcs-1]
            sop,ssop,icent,cent,unit = G2spc.OpsfromStringOps(opr,SGData,SSGData)
            drxyz = (np.inner(sop[0],atxyz)+sop[1]+cent)*icent+np.array(unit)
            tauT = G2spc.getTauT(tau,sop,ssop,drxyz,modul)[-1]
            tauT *= icent       #invert wave on -1
#            print(tau,tauT,opr,G2spc.MT2text(sop).replace(' ',''),G2spc.SSMT2text(ssop).replace(' ',''))
            wave = np.zeros(3)
            uwave = np.zeros(6)
            mom = np.zeros(3)
            if len(Sfrac):
                scof = []
                ccof = []
                waveType = Sfrac[0]
                for i,sfrac in enumerate(Sfrac[1:]):
                    if not i and 'Crenel' in waveType:
                        Fade[ind] += fracCrenel(tauT,sfrac[0][0],sfrac[0][1])
                    else:
                        scof.append(sfrac[0][0])
                        ccof.append(sfrac[0][1])
                    if len(scof):
                        Fade[ind] += np.sum(fracFourier(tauT,scof,ccof))                            
            if len(Spos):
                scof = []
                ccof = []
                waveType = Spos[0]
                for i,spos in enumerate(Spos[1:]):
                    if waveType in ['ZigZag','Block'] and not i:
                        Tminmax = spos[0][:2]
                        XYZmax = np.array(spos[0][2:5])
                        if waveType == 'Block':
                            wave = np.array(posBlock([tauT,],Tminmax,XYZmax))[0]
                        elif waveType == 'ZigZag':
                            wave = np.array(posZigZag([tauT,],Tminmax,XYZmax))[0]
                    else:
                        scof.append(spos[0][:3])
                        ccof.append(spos[0][3:])
                if len(scof):
                    wave += np.sum(posFourier(tauT,np.array(scof),np.array(ccof)),axis=1)
            if generalData['Type'] == 'magnetic' and len(Smag):
                scof = []
                ccof = []
                waveType = Smag[0]
                for i,spos in enumerate(Smag[1:]):
                    scof.append(spos[0][:3])
                    ccof.append(spos[0][3:])
                if len(scof):
                    mom += np.sum(posFourier(tauT,np.array(scof),np.array(ccof)),axis=1)
            if len(Sadp):
                scof = []
                ccof = []
                waveType = Sadp[0]
                for i,sadp in enumerate(Sadp[1:]):
                    scof.append(sadp[0][:6])
                    ccof.append(sadp[0][6:])
                ures = posFourier(tauT,np.array(scof),np.array(ccof))
                if np.any(ures):
                    uwave += np.sum(ures,axis=1)
            if atom[cia] == 'A':                    
                X,U = G2spc.ApplyStringOps(opr,SGData,atxyz+wave,atuij+uwave)
                drawatom[dcx:dcx+3] = X
                drawatom[dci-6:dci] = U
            else:
                X = G2spc.ApplyStringOps(opr,SGData,atxyz+wave)
                drawatom[dcx:dcx+3] = X
            if generalData['Type'] == 'magnetic':
                M = G2spc.ApplyStringOpsMom(opr,SGData,atmom+mom)
                drawatom[dcx+3:dcx+6] = M
    return drawAtoms,Fade
    
# gauleg.py Gauss Legendre numerical quadrature, x and w computation 
# integrate from a to b using n evaluations of the function f(x)  
# usage: from gauleg import gaulegf         
#        x,w = gaulegf( a, b, n)                                
#        area = 0.0                                            
#        for i in range(1,n+1):          #  yes, 1..n                   
#          area += w[i]*f(x[i])                                    

def gaulegf(a, b, n):
    x = range(n+1) # x[0] unused
    w = range(n+1) # w[0] unused
    eps = 3.0E-14
    m = (n+1)/2
    xm = 0.5*(b+a)
    xl = 0.5*(b-a)
    for i in range(1,m+1):
        z = math.cos(3.141592654*(i-0.25)/(n+0.5))
        while True:
            p1 = 1.0
            p2 = 0.0
            for j in range(1,n+1):
                p3 = p2
                p2 = p1
                p1 = ((2.0*j-1.0)*z*p2-(j-1.0)*p3)/j
        
            pp = n*(z*p1-p2)/(z*z-1.0)
            z1 = z
            z = z1 - p1/pp
            if abs(z-z1) <= eps:
                break

        x[i] = xm - xl*z
        x[n+1-i] = xm + xl*z
        w[i] = 2.0*xl/((1.0-z*z)*pp*pp)
        w[n+1-i] = w[i]
    return np.array(x), np.array(w)
# end gaulegf 
    
    
def BessJn(nmax,x):
    ''' compute Bessel function J(n,x) from scipy routine & recurrance relation
    returns sequence of J(n,x) for n in range [-nmax...0...nmax]
    
    :param  integer nmax: maximul order for Jn(x)
    :param  float x: argument for Jn(x)
    
    :returns numpy array: [J(-nmax,x)...J(0,x)...J(nmax,x)]
    
    '''
    import scipy.special as sp
    bessJn = np.zeros(2*nmax+1)
    bessJn[nmax] = sp.j0(x)
    bessJn[nmax+1] = sp.j1(x)
    bessJn[nmax-1] = -bessJn[nmax+1]
    for i in range(2,nmax+1):
        bessJn[i+nmax] = 2*(i-1)*bessJn[nmax+i-1]/x-bessJn[nmax+i-2]
        bessJn[nmax-i] = bessJn[i+nmax]*(-1)**i
    return bessJn
    
def BessIn(nmax,x):
    ''' compute modified Bessel function I(n,x) from scipy routines & recurrance relation
    returns sequence of I(n,x) for n in range [-nmax...0...nmax]
    
    :param  integer nmax: maximul order for In(x)
    :param  float x: argument for In(x)
    
    :returns numpy array: [I(-nmax,x)...I(0,x)...I(nmax,x)]
    
    '''
    import scipy.special as sp
    bessIn = np.zeros(2*nmax+1)
    bessIn[nmax] = sp.i0(x)
    bessIn[nmax+1] = sp.i1(x)
    bessIn[nmax-1] = bessIn[nmax+1]
    for i in range(2,nmax+1):
        bessIn[i+nmax] = bessIn[nmax+i-2]-2*(i-1)*bessIn[nmax+i-1]/x
        bessIn[nmax-i] = bessIn[i+nmax]
    return bessIn
        
    
################################################################################
##### distance, angle, planes, torsion stuff 
################################################################################

def CalcDist(distance_dict, distance_atoms, parmDict):
    if not len(parmDict):
        return 0.
    pId = distance_dict['pId']
    A = [parmDict['%s::A%d'%(pId,i)] for i in range(6)]
    Amat = G2lat.cell2AB(G2lat.A2cell(A))[0]
    Oxyz = [parmDict['%s::A%s:%d'%(pId,x,distance_atoms[0])] for x in ['x','y','z']]
    Txyz = [parmDict['%s::A%s:%d'%(pId,x,distance_atoms[1])] for x in ['x','y','z']]
    inv = 1
    symNo = distance_dict['symNo']
    if symNo < 0:
        inv = -1
        symNo *= -1
    cen = symNo//100
    op = symNo%100-1
    M,T = distance_dict['SGData']['SGOps'][op]
    D = T*inv+distance_dict['SGData']['SGCen'][cen]
    D += distance_dict['cellNo']
    Txyz = np.inner(M*inv,Txyz)+D
    dist = np.sqrt(np.sum(np.inner(Amat,(Txyz-Oxyz))**2))
#    GSASIIpath.IPyBreak()
    return dist    
    
def CalcDistDeriv(distance_dict, distance_atoms, parmDict):
    if not len(parmDict):
        return None
    pId = distance_dict['pId']
    A = [parmDict['%s::A%d'%(pId,i)] for i in range(6)]
    Amat = G2lat.cell2AB(G2lat.A2cell(A))[0]
    Oxyz = [parmDict['%s::A%s:%d'%(pId,x,distance_atoms[0])] for x in ['x','y','z']]
    Txyz = [parmDict['%s::A%s:%d'%(pId,x,distance_atoms[1])] for x in ['x','y','z']]
    symNo = distance_dict['symNo']
    Tunit = distance_dict['cellNo']
    SGData = distance_dict['SGData']    
    deriv = getDistDerv(Oxyz,Txyz,Amat,Tunit,symNo,SGData)
    return deriv
   
def CalcAngle(angle_dict, angle_atoms, parmDict):
    if not len(parmDict):
        return 0.
    pId = angle_dict['pId']
    A = [parmDict['%s::A%d'%(pId,i)] for i in range(6)]
    Amat = G2lat.cell2AB(G2lat.A2cell(A))[0]
    Oxyz = [parmDict['%s::A%s:%d'%(pId,x,angle_atoms[0])] for x in ['x','y','z']]
    Axyz = [parmDict['%s::A%s:%d'%(pId,x,angle_atoms[1][0])] for x in ['x','y','z']]
    Bxyz = [parmDict['%s::A%s:%d'%(pId,x,angle_atoms[1][1])] for x in ['x','y','z']]
    ABxyz = [Axyz,Bxyz]
    symNo = angle_dict['symNo']
    vec = np.zeros((2,3))
    for i in range(2):
        inv = 1
        if symNo[i] < 0:
            inv = -1
        cen = inv*symNo[i]//100
        op = inv*symNo[i]%100-1
        M,T = angle_dict['SGData']['SGOps'][op]
        D = T*inv+angle_dict['SGData']['SGCen'][cen]
        D += angle_dict['cellNo'][i]
        ABxyz[i] = np.inner(M*inv,ABxyz[i])+D
        vec[i] = np.inner(Amat,(ABxyz[i]-Oxyz))
        dist = np.sqrt(np.sum(vec[i]**2))
        if not dist:
            return 0.
        vec[i] /= dist
    angle = acosd(np.sum(vec[0]*vec[1]))
#    GSASIIpath.IPyBreak()
    return angle

def CalcAngleDeriv(angle_dict, angle_atoms, parmDict):
    if not len(parmDict):
        return None
    pId = angle_dict['pId']
    A = [parmDict['%s::A%d'%(pId,i)] for i in range(6)]
    Amat = G2lat.cell2AB(G2lat.A2cell(A))[0]
    Oxyz = [parmDict['%s::A%s:%d'%(pId,x,angle_atoms[0])] for x in ['x','y','z']]
    Axyz = [parmDict['%s::A%s:%d'%(pId,x,angle_atoms[1][0])] for x in ['x','y','z']]
    Bxyz = [parmDict['%s::A%s:%d'%(pId,x,angle_atoms[1][1])] for x in ['x','y','z']]
    symNo = angle_dict['symNo']
    Tunit = angle_dict['cellNo']
    SGData = angle_dict['SGData']    
    deriv = getAngleDerv(Oxyz,Axyz,Bxyz,Amat,Tunit,symNo,SGData)
    return deriv

def getSyXYZ(XYZ,ops,SGData):
    '''default doc 
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    XYZout = np.zeros_like(XYZ)
    for i,[xyz,op] in enumerate(zip(XYZ,ops)):
        if op == '1':
            XYZout[i] = xyz
        else:
            oprs = op.split('+')
            unit = [0,0,0]
            if len(oprs)>1:
                unit = np.array(list(eval(oprs[1])))
            syop =int(oprs[0])
            inv = syop//abs(syop)
            syop *= inv
            cent = syop//100
            syop %= 100
            syop -= 1
            M,T = SGData['SGOps'][syop]
            XYZout[i] = (np.inner(M,xyz)+T)*inv+SGData['SGCen'][cent]+unit
    return XYZout
    
def getRestDist(XYZ,Amat):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    return np.sqrt(np.sum(np.inner(Amat,(XYZ[1]-XYZ[0]))**2))
    
def getRestDeriv(Func,XYZ,Amat,ops,SGData):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    deriv = np.zeros((len(XYZ),3))
    dx = 0.00001
    for j,xyz in enumerate(XYZ):
        for i,x in enumerate(np.array([[dx,0,0],[0,dx,0],[0,0,dx]])):
            XYZ[j] -= x
            d1 = Func(getSyXYZ(XYZ,ops,SGData),Amat)
            XYZ[j] += 2*x
            d2 = Func(getSyXYZ(XYZ,ops,SGData),Amat)
            XYZ[j] -= x
            deriv[j][i] = (d1-d2)/(2*dx)
    return deriv.flatten()

def getRestAngle(XYZ,Amat):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    
    def calcVec(Ox,Tx,Amat):
        return np.inner(Amat,(Tx-Ox))

    VecA = calcVec(XYZ[1],XYZ[0],Amat)
    VecA /= np.sqrt(np.sum(VecA**2))
    VecB = calcVec(XYZ[1],XYZ[2],Amat)
    VecB /= np.sqrt(np.sum(VecB**2))
    edge = VecB-VecA
    edge = np.sum(edge**2)
    angle = (2.-edge)/2.
    angle = max(angle,-1.)
    return acosd(angle)
    
def getRestPlane(XYZ,Amat):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    sumXYZ = np.zeros(3)
    for xyz in XYZ:
        sumXYZ += xyz
    sumXYZ /= len(XYZ)
    XYZ = np.array(XYZ)-sumXYZ
    XYZ = np.inner(Amat,XYZ).T
    Zmat = np.zeros((3,3))
    for i,xyz in enumerate(XYZ):
        Zmat += np.outer(xyz.T,xyz)
    Evec,Emat = nl.eig(Zmat)
    Evec = np.sqrt(Evec)/(len(XYZ)-3)
    Order = np.argsort(Evec)
    return Evec[Order[0]]
    
def getRestChiral(XYZ,Amat):    
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    VecA = np.empty((3,3))    
    VecA[0] = np.inner(XYZ[1]-XYZ[0],Amat)
    VecA[1] = np.inner(XYZ[2]-XYZ[0],Amat)
    VecA[2] = np.inner(XYZ[3]-XYZ[0],Amat)
    return nl.det(VecA)
    
def getRestTorsion(XYZ,Amat):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    VecA = np.empty((3,3))
    VecA[0] = np.inner(XYZ[1]-XYZ[0],Amat)
    VecA[1] = np.inner(XYZ[2]-XYZ[1],Amat)
    VecA[2] = np.inner(XYZ[3]-XYZ[2],Amat)
    D = nl.det(VecA)
    Mag = np.sqrt(np.sum(VecA*VecA,axis=1))
    P12 = np.sum(VecA[0]*VecA[1])/(Mag[0]*Mag[1])
    P13 = np.sum(VecA[0]*VecA[2])/(Mag[0]*Mag[2])
    P23 = np.sum(VecA[1]*VecA[2])/(Mag[1]*Mag[2])
    Ang = 1.0
    if abs(P12) < 1.0 and abs(P23) < 1.0:
        Ang = (P12*P23-P13)/(np.sqrt(1.-P12**2)*np.sqrt(1.-P23**2))
    TOR = (acosd(Ang)*D/abs(D)+720.)%360.
    return TOR
    
def calcTorsionEnergy(TOR,Coeff=[]):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    sum = 0.
    if len(Coeff):
        cof = np.reshape(Coeff,(3,3)).T
        delt = TOR-cof[1]
        delt = np.where(delt<-180.,delt+360.,delt)
        delt = np.where(delt>180.,delt-360.,delt)
        term = -cof[2]*delt**2
        val = cof[0]*np.exp(term/1000.0)
        pMax = cof[0][np.argmin(val)]
        Eval = np.sum(val)
        sum = Eval-pMax
    return sum,Eval

def getTorsionDeriv(XYZ,Amat,Coeff):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    deriv = np.zeros((len(XYZ),3))
    dx = 0.00001
    for j,xyz in enumerate(XYZ):
        for i,x in enumerate(np.array([[dx,0,0],[0,dx,0],[0,0,dx]])):
            XYZ[j] -= x
            tor = getRestTorsion(XYZ,Amat)
            p1,d1 = calcTorsionEnergy(tor,Coeff)
            XYZ[j] += 2*x
            tor = getRestTorsion(XYZ,Amat)
            p2,d2 = calcTorsionEnergy(tor,Coeff)            
            XYZ[j] -= x
            deriv[j][i] = (p2-p1)/(2*dx)
    return deriv.flatten()

def getRestRama(XYZ,Amat):
    '''Computes a pair of torsion angles in a 5 atom string
    
    :param nparray XYZ: crystallographic coordinates of 5 atoms
    :param nparray Amat: crystal to cartesian transformation matrix
    
    :returns: list (phi,psi) two torsion angles in degrees
    
    '''
    phi = getRestTorsion(XYZ[:5],Amat)
    psi = getRestTorsion(XYZ[1:],Amat)
    return phi,psi
    
def calcRamaEnergy(phi,psi,Coeff=[]):
    '''Computes pseudo potential energy from a pair of torsion angles and a
    numerical description of the potential energy surface. Used to create 
    penalty function in LS refinement:     
    :math:`Eval(\\phi,\\psi) = C[0]*exp(-V/1000)`

    where :math:`V = -C[3] * (\\phi-C[1])^2 - C[4]*(\\psi-C[2])^2 - 2*(\\phi-C[1])*(\\psi-C[2])`
    
    :param float phi: first torsion angle (:math:`\\phi`)
    :param float psi: second torsion angle (:math:`\\psi`)
    :param list Coeff: pseudo potential coefficients
    
    :returns: list (sum,Eval): pseudo-potential difference from minimum & value;
      sum is used for penalty function.
    
    '''
    sum = 0.
    Eval = 0.
    if len(Coeff):
        cof = Coeff.T
        dPhi = phi-cof[1]
        dPhi = np.where(dPhi<-180.,dPhi+360.,dPhi)
        dPhi = np.where(dPhi>180.,dPhi-360.,dPhi)
        dPsi = psi-cof[2]
        dPsi = np.where(dPsi<-180.,dPsi+360.,dPsi)
        dPsi = np.where(dPsi>180.,dPsi-360.,dPsi)
        val = -cof[3]*dPhi**2-cof[4]*dPsi**2-2.0*cof[5]*dPhi*dPsi
        val = cof[0]*np.exp(val/1000.)
        pMax = cof[0][np.argmin(val)]
        Eval = np.sum(val)
        sum = Eval-pMax
    return sum,Eval

def getRamaDeriv(XYZ,Amat,Coeff):
    '''Computes numerical derivatives of torsion angle pair pseudo potential
    with respect of crystallographic atom coordinates of the 5 atom sequence 
    
    :param nparray XYZ: crystallographic coordinates of 5 atoms
    :param nparray Amat: crystal to cartesian transformation matrix
    :param list Coeff: pseudo potential coefficients
    
    :returns: list (deriv) derivatives of pseudopotential with respect to 5 atom
     crystallographic xyz coordinates.
    
    '''
    deriv = np.zeros((len(XYZ),3))
    dx = 0.00001
    for j,xyz in enumerate(XYZ):
        for i,x in enumerate(np.array([[dx,0,0],[0,dx,0],[0,0,dx]])):
            XYZ[j] -= x
            phi,psi = getRestRama(XYZ,Amat)
            p1,d1 = calcRamaEnergy(phi,psi,Coeff)
            XYZ[j] += 2*x
            phi,psi = getRestRama(XYZ,Amat)
            p2,d2 = calcRamaEnergy(phi,psi,Coeff)
            XYZ[j] -= x
            deriv[j][i] = (p2-p1)/(2*dx)
    return deriv.flatten()

def getRestPolefig(ODFln,SamSym,Grid):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    X,Y = np.meshgrid(np.linspace(1.,-1.,Grid),np.linspace(-1.,1.,Grid))
    R,P = np.sqrt(X**2+Y**2).flatten(),atan2d(Y,X).flatten()
    R = np.where(R <= 1.,2.*atand(R),0.0)
    Z = np.zeros_like(R)
    Z = G2lat.polfcal(ODFln,SamSym,R,P)
    Z = np.reshape(Z,(Grid,Grid))
    return np.reshape(R,(Grid,Grid)),np.reshape(P,(Grid,Grid)),Z

def getRestPolefigDerv(HKL,Grid,SHCoeff):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    pass
        
def getDistDerv(Oxyz,Txyz,Amat,Tunit,Top,SGData):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    def calcDist(Ox,Tx,U,inv,C,M,T,Amat):
        TxT = inv*(np.inner(M,Tx)+T)+C+U
        return np.sqrt(np.sum(np.inner(Amat,(TxT-Ox))**2))
        
    inv = Top/abs(Top)
    cent = abs(Top)//100
    op = abs(Top)%100-1
    M,T = SGData['SGOps'][op]
    C = SGData['SGCen'][cent]
    dx = .00001
    deriv = np.zeros(6)
    for i in [0,1,2]:
        Oxyz[i] -= dx
        d0 = calcDist(Oxyz,Txyz,Tunit,inv,C,M,T,Amat)
        Oxyz[i] += 2*dx
        deriv[i] = (calcDist(Oxyz,Txyz,Tunit,inv,C,M,T,Amat)-d0)/(2.*dx)
        Oxyz[i] -= dx
        Txyz[i] -= dx
        d0 = calcDist(Oxyz,Txyz,Tunit,inv,C,M,T,Amat)
        Txyz[i] += 2*dx
        deriv[i+3] = (calcDist(Oxyz,Txyz,Tunit,inv,C,M,T,Amat)-d0)/(2.*dx)
        Txyz[i] -= dx
    return deriv
    
def getAngleDerv(Oxyz,Axyz,Bxyz,Amat,Tunit,symNo,SGData):
    
    def calcAngle(Oxyz,ABxyz,Amat,Tunit,symNo,SGData):
        vec = np.zeros((2,3))
        for i in range(2):
            inv = 1
            if symNo[i] < 0:
                inv = -1
            cen = inv*symNo[i]//100
            op = inv*symNo[i]%100-1
            M,T = SGData['SGOps'][op]
            D = T*inv+SGData['SGCen'][cen]
            D += Tunit[i]
            ABxyz[i] = np.inner(M*inv,ABxyz[i])+D
            vec[i] = np.inner(Amat,(ABxyz[i]-Oxyz))
            dist = np.sqrt(np.sum(vec[i]**2))
            if not dist:
                return 0.
            vec[i] /= dist
        angle = acosd(np.sum(vec[0]*vec[1]))
    #    GSASIIpath.IPyBreak()
        return angle
        
    dx = .00001
    deriv = np.zeros(9)
    for i in [0,1,2]:
        Oxyz[i] -= dx
        a0 = calcAngle(Oxyz,[Axyz,Bxyz],Amat,Tunit,symNo,SGData)
        Oxyz[i] += 2*dx
        deriv[i] = (calcAngle(Oxyz,[Axyz,Bxyz],Amat,Tunit,symNo,SGData)-a0)/(2.*dx)
        Oxyz[i] -= dx
        Axyz[i] -= dx
        a0 = calcAngle(Oxyz,[Axyz,Bxyz],Amat,Tunit,symNo,SGData)
        Axyz[i] += 2*dx
        deriv[i+3] = (calcAngle(Oxyz,[Axyz,Bxyz],Amat,Tunit,symNo,SGData)-a0)/(2.*dx)
        Axyz[i] -= dx
        Bxyz[i] -= dx
        a0 = calcAngle(Oxyz,[Axyz,Bxyz],Amat,Tunit,symNo,SGData)
        Bxyz[i] += 2*dx
        deriv[i+6] = (calcAngle(Oxyz,[Axyz,Bxyz],Amat,Tunit,symNo,SGData)-a0)/(2.*dx)
        Bxyz[i] -= dx
    return deriv
    
def getAngSig(VA,VB,Amat,SGData,covData={}):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    def calcVec(Ox,Tx,U,inv,C,M,T,Amat):
        TxT = inv*(np.inner(M,Tx)+T)+C+U
        return np.inner(Amat,(TxT-Ox))
        
    def calcAngle(Ox,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat):
        VecA = calcVec(Ox,TxA,unitA,invA,CA,MA,TA,Amat)
        VecA /= np.sqrt(np.sum(VecA**2))
        VecB = calcVec(Ox,TxB,unitB,invB,CB,MB,TB,Amat)
        VecB /= np.sqrt(np.sum(VecB**2))
        edge = VecB-VecA
        edge = np.sum(edge**2)
        angle = (2.-edge)/2.
        angle = max(angle,-1.)
        return acosd(angle)
        
    OxAN,OxA,TxAN,TxA,unitA,TopA = VA
    OxBN,OxB,TxBN,TxB,unitB,TopB = VB
    invA = invB = 1
    invA = TopA//abs(TopA)
    invB = TopB//abs(TopB)
    centA = abs(TopA)//100
    centB = abs(TopB)//100
    opA = abs(TopA)%100-1
    opB = abs(TopB)%100-1
    MA,TA = SGData['SGOps'][opA]
    MB,TB = SGData['SGOps'][opB]
    CA = SGData['SGCen'][centA]
    CB = SGData['SGCen'][centB]
    if 'covMatrix' in covData:
        covMatrix = covData['covMatrix']
        varyList = covData['varyList']
        AngVcov = getVCov(OxAN+TxAN+TxBN,varyList,covMatrix)
        dx = .00001
        dadx = np.zeros(9)
        Ang = calcAngle(OxA,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat)
        for i in [0,1,2]:
            OxA[i] -= dx
            a0 = calcAngle(OxA,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat)
            OxA[i] += 2*dx
            dadx[i] = (calcAngle(OxA,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat)-a0)/(2*dx)
            OxA[i] -= dx
            
            TxA[i] -= dx
            a0 = calcAngle(OxA,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat)
            TxA[i] += 2*dx
            dadx[i+3] = (calcAngle(OxA,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat)-a0)/(2*dx)
            TxA[i] -= dx
            
            TxB[i] -= dx
            a0 = calcAngle(OxA,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat)
            TxB[i] += 2*dx
            dadx[i+6] = (calcAngle(OxA,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat)-a0)/(2*dx)
            TxB[i] -= dx
            
        sigAng = np.sqrt(np.inner(dadx,np.inner(AngVcov,dadx)))
        if sigAng < 0.01:
            sigAng = 0.0
        return Ang,sigAng
    else:
        return calcAngle(OxA,TxA,TxB,unitA,unitB,invA,CA,MA,TA,invB,CB,MB,TB,Amat),0.0

def GetDistSig(Oatoms,Atoms,Amat,SGData,covData={}):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    def calcDist(Atoms,SyOps,Amat):
        XYZ = []
        for i,atom in enumerate(Atoms):
            Inv,M,T,C,U = SyOps[i]
            XYZ.append(np.array(atom[1:4]))
            XYZ[-1] = Inv*(np.inner(M,np.array(XYZ[-1]))+T)+C+U
            XYZ[-1] = np.inner(Amat,XYZ[-1]).T
        V1 = XYZ[1]-XYZ[0]
        return np.sqrt(np.sum(V1**2))
        
    SyOps = []
    names = []
    for i,atom in enumerate(Oatoms):
        names += atom[-1]
        Op,unit = Atoms[i][-1]
        inv = Op//abs(Op)
        m,t = SGData['SGOps'][abs(Op)%100-1]
        c = SGData['SGCen'][abs(Op)//100]
        SyOps.append([inv,m,t,c,unit])
    Dist = calcDist(Oatoms,SyOps,Amat)
    
    sig = -0.001
    if 'covMatrix' in covData:
        dx = .00001
        dadx = np.zeros(6)
        for i in range(6):
            ia = i//3
            ix = i%3
            Oatoms[ia][ix+1] += dx
            a0 = calcDist(Oatoms,SyOps,Amat)
            Oatoms[ia][ix+1] -= 2*dx
            dadx[i] = (calcDist(Oatoms,SyOps,Amat)-a0)/(2.*dx)
        covMatrix = covData['covMatrix']
        varyList = covData['varyList']
        DistVcov = getVCov(names,varyList,covMatrix)
        sig = np.sqrt(np.inner(dadx,np.inner(DistVcov,dadx)))
        if sig < 0.001:
            sig = -0.001
    
    return Dist,sig

def GetAngleSig(Oatoms,Atoms,Amat,SGData,covData={}):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''

    def calcAngle(Atoms,SyOps,Amat):
        XYZ = []
        for i,atom in enumerate(Atoms):
            Inv,M,T,C,U = SyOps[i]
            XYZ.append(np.array(atom[1:4]))
            XYZ[-1] = Inv*(np.inner(M,np.array(XYZ[-1]))+T)+C+U
            XYZ[-1] = np.inner(Amat,XYZ[-1]).T
        V1 = XYZ[1]-XYZ[0]
        V1 /= np.sqrt(np.sum(V1**2))
        V2 = XYZ[1]-XYZ[2]
        V2 /= np.sqrt(np.sum(V2**2))
        V3 = V2-V1
        cang = min(1.,max((2.-np.sum(V3**2))/2.,-1.))
        return acosd(cang)

    SyOps = []
    names = []
    for i,atom in enumerate(Oatoms):
        names += atom[-1]
        Op,unit = Atoms[i][-1]
        inv = Op//abs(Op)
        m,t = SGData['SGOps'][abs(Op)%100-1]
        c = SGData['SGCen'][abs(Op)//100]
        SyOps.append([inv,m,t,c,unit])
    Angle = calcAngle(Oatoms,SyOps,Amat)
    
    sig = -0.01
    if 'covMatrix' in covData:
        dx = .00001
        dadx = np.zeros(9)
        for i in range(9):
            ia = i//3
            ix = i%3
            Oatoms[ia][ix+1] += dx
            a0 = calcAngle(Oatoms,SyOps,Amat)
            Oatoms[ia][ix+1] -= 2*dx
            dadx[i] = (calcAngle(Oatoms,SyOps,Amat)-a0)/(2.*dx)
        covMatrix = covData['covMatrix']
        varyList = covData['varyList']
        AngVcov = getVCov(names,varyList,covMatrix)
        sig = np.sqrt(np.inner(dadx,np.inner(AngVcov,dadx)))
        if sig < 0.01:
            sig = -0.01
    
    return Angle,sig

def GetTorsionSig(Oatoms,Atoms,Amat,SGData,covData={}):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''

    def calcTorsion(Atoms,SyOps,Amat):
        
        XYZ = []
        for i,atom in enumerate(Atoms):
            Inv,M,T,C,U = SyOps[i]
            XYZ.append(np.array(atom[1:4]))
            XYZ[-1] = Inv*(np.inner(M,np.array(XYZ[-1]))+T)+C+U
            XYZ[-1] = np.inner(Amat,XYZ[-1]).T
        V1 = XYZ[1]-XYZ[0]
        V2 = XYZ[2]-XYZ[1]
        V3 = XYZ[3]-XYZ[2]
        V1 /= np.sqrt(np.sum(V1**2))
        V2 /= np.sqrt(np.sum(V2**2))
        V3 /= np.sqrt(np.sum(V3**2))
        M = np.array([V1,V2,V3])
        D = nl.det(M)
        P12 = np.dot(V1,V2)
        P13 = np.dot(V1,V3)
        P23 = np.dot(V2,V3)
        Tors = acosd((P12*P23-P13)/(np.sqrt(1.-P12**2)*np.sqrt(1.-P23**2)))*D/abs(D)
        return Tors
            
    SyOps = []
    names = []
    for i,atom in enumerate(Oatoms):
        names += atom[-1]
        Op,unit = Atoms[i][-1]
        inv = Op//abs(Op)
        m,t = SGData['SGOps'][abs(Op)%100-1]
        c = SGData['SGCen'][abs(Op)//100]
        SyOps.append([inv,m,t,c,unit])
    Tors = calcTorsion(Oatoms,SyOps,Amat)
    
    sig = -0.01
    if 'covMatrix' in covData:
        dx = .00001
        dadx = np.zeros(12)
        for i in range(12):
            ia = i//3
            ix = i%3
            Oatoms[ia][ix+1] -= dx
            a0 = calcTorsion(Oatoms,SyOps,Amat)
            Oatoms[ia][ix+1] += 2*dx
            dadx[i] = (calcTorsion(Oatoms,SyOps,Amat)-a0)/(2.*dx)
            Oatoms[ia][ix+1] -= dx            
        covMatrix = covData['covMatrix']
        varyList = covData['varyList']
        TorVcov = getVCov(names,varyList,covMatrix)
        sig = np.sqrt(np.inner(dadx,np.inner(TorVcov,dadx)))
        if sig < 0.01:
            sig = -0.01
    
    return Tors,sig
        
def GetDATSig(Oatoms,Atoms,Amat,SGData,covData={}):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''

    def calcDist(Atoms,SyOps,Amat):
        XYZ = []
        for i,atom in enumerate(Atoms):
            Inv,M,T,C,U = SyOps[i]
            XYZ.append(np.array(atom[1:4]))
            XYZ[-1] = Inv*(np.inner(M,np.array(XYZ[-1]))+T)+C+U
            XYZ[-1] = np.inner(Amat,XYZ[-1]).T
        V1 = XYZ[1]-XYZ[0]
        return np.sqrt(np.sum(V1**2))
        
    def calcAngle(Atoms,SyOps,Amat):
        XYZ = []
        for i,atom in enumerate(Atoms):
            Inv,M,T,C,U = SyOps[i]
            XYZ.append(np.array(atom[1:4]))
            XYZ[-1] = Inv*(np.inner(M,np.array(XYZ[-1]))+T)+C+U
            XYZ[-1] = np.inner(Amat,XYZ[-1]).T
        V1 = XYZ[1]-XYZ[0]
        V1 /= np.sqrt(np.sum(V1**2))
        V2 = XYZ[1]-XYZ[2]
        V2 /= np.sqrt(np.sum(V2**2))
        V3 = V2-V1
        cang = min(1.,max((2.-np.sum(V3**2))/2.,-1.))
        return acosd(cang)

    def calcTorsion(Atoms,SyOps,Amat):
        
        XYZ = []
        for i,atom in enumerate(Atoms):
            Inv,M,T,C,U = SyOps[i]
            XYZ.append(np.array(atom[1:4]))
            XYZ[-1] = Inv*(np.inner(M,np.array(XYZ[-1]))+T)+C+U
            XYZ[-1] = np.inner(Amat,XYZ[-1]).T
        V1 = XYZ[1]-XYZ[0]
        V2 = XYZ[2]-XYZ[1]
        V3 = XYZ[3]-XYZ[2]
        V1 /= np.sqrt(np.sum(V1**2))
        V2 /= np.sqrt(np.sum(V2**2))
        V3 /= np.sqrt(np.sum(V3**2))
        M = np.array([V1,V2,V3])
        D = nl.det(M)
        P12 = np.dot(V1,V2)
        P13 = np.dot(V1,V3)
        P23 = np.dot(V2,V3)
        Tors = acosd((P12*P23-P13)/(np.sqrt(1.-P12**2)*np.sqrt(1.-P23**2)))*D/abs(D)
        return Tors
            
    SyOps = []
    names = []
    for i,atom in enumerate(Oatoms):
        names += atom[-1]
        Op,unit = Atoms[i][-1]
        inv = Op//abs(Op)
        m,t = SGData['SGOps'][abs(Op)%100-1]
        c = SGData['SGCen'][abs(Op)//100]
        SyOps.append([inv,m,t,c,unit])
    M = len(Oatoms)
    if M == 2:
        Val = calcDist(Oatoms,SyOps,Amat)
    elif M == 3:
        Val = calcAngle(Oatoms,SyOps,Amat)
    else:
        Val = calcTorsion(Oatoms,SyOps,Amat)
    
    sigVals = [-0.001,-0.01,-0.01]
    sig = sigVals[M-3]
    if 'covMatrix' in covData:
        dx = .00001
        N = M*3
        dadx = np.zeros(N)
        for i in range(N):
            ia = i//3
            ix = i%3
            Oatoms[ia][ix+1] += dx
            if M == 2:
                a0 = calcDist(Oatoms,SyOps,Amat)
            elif M == 3:
                a0 = calcAngle(Oatoms,SyOps,Amat)
            else:
                a0 = calcTorsion(Oatoms,SyOps,Amat)
            Oatoms[ia][ix+1] -= 2*dx
            if M == 2:
                dadx[i] = (calcDist(Oatoms,SyOps,Amat)-a0)/(2.*dx)                
            elif M == 3:
                dadx[i] = (calcAngle(Oatoms,SyOps,Amat)-a0)/(2.*dx)                
            else:
                dadx[i] = (calcTorsion(Oatoms,SyOps,Amat)-a0)/(2.*dx)
        covMatrix = covData['covMatrix']
        varyList = covData['varyList']
        Vcov = getVCov(names,varyList,covMatrix)
        sig = np.sqrt(np.inner(dadx,np.inner(Vcov,dadx)))
        if sig < sigVals[M-3]:
            sig = sigVals[M-3]
    
    return Val,sig
        
def ValEsd(value,esd=0,nTZ=False):
    '''Format a floating point number with a given level of precision or
    with in crystallographic format with a "esd", as value(esd). If esd is
    negative the number is formatted with the level of significant figures
    appropriate if abs(esd) were the esd, but the esd is not included.
    if the esd is zero, approximately 6 significant figures are printed.
    nTZ=True causes "extra" zeros to be removed after the decimal place.
    for example:

      * "1.235(3)" for value=1.2346 & esd=0.003
      * "1.235(3)e4" for value=12346. & esd=30
      * "1.235(3)e6" for value=0.12346e7 & esd=3000
      * "1.235" for value=1.2346 & esd=-0.003
      * "1.240" for value=1.2395 & esd=-0.003
      * "1.24" for value=1.2395 & esd=-0.003 with nTZ=True
      * "1.23460" for value=1.2346 & esd=0.0

    :param float value: number to be formatted
    :param float esd: uncertainty or if esd < 0, specifies level of
      precision to be shown e.g. esd=-0.01 gives 2 places beyond decimal
    :param bool nTZ: True to remove trailing zeros (default is False)
    :returns: value(esd) or value as a string

    '''
    # Note: this routine is Python 3 compatible -- I think
    cutoff = 3.16228    #=(sqrt(10); same as old GSAS   was 1.95
    if math.isnan(value): # invalid value, bail out
        return '?'
    if math.isnan(esd): # invalid esd, treat as zero
        esd = 0
        esdoff = 5
#    if esd < 1.e-5:
#        esd = 0
#        esdoff = 5
    elif esd != 0:
        # transform the esd to a one or two digit integer
        l = math.log10(abs(esd)) % 1.
        if l < math.log10(cutoff): l+= 1.        
        intesd = int(round(10**l)) # esd as integer
        # determine the number of digits offset for the esd
        esdoff = int(round(math.log10(intesd*1./abs(esd))))
    else:
        esdoff = 5
    valoff = 0
    if abs(value) < abs(esdoff): # value is effectively zero
        pass
    elif esdoff < 0 or abs(value) > 1.0e6 or abs(value) < 1.0e-4: # use scientific notation
        # where the digit offset is to the left of the decimal place or where too many
        # digits are needed
        if abs(value) > 1:
            valoff = int(math.log10(abs(value)))
        elif abs(value) > 0:
            valoff = int(math.log10(abs(value))-0.9999999)
        else:
            valoff = 0
    if esd != 0:
        if valoff+esdoff < 0:
            valoff = esdoff = 0
        out = ("{:."+str(valoff+esdoff)+"f}").format(value/10**valoff) # format the value
    elif valoff != 0: # esd = 0; exponential notation ==> esdoff decimal places
        out = ("{:."+str(esdoff)+"f}").format(value/10**valoff) # format the value
    else: # esd = 0; non-exponential notation ==> esdoff+1 significant digits
        if abs(value) > 0:            
            extra = -math.log10(abs(value))
        else:
            extra = 0
        if extra > 0: extra += 1
        out = ("{:."+str(max(0,esdoff+int(extra)))+"f}").format(value) # format the value
    if esd > 0:
        out += ("({:d})").format(intesd)  # add the esd
    elif nTZ and '.' in out:
        out = out.rstrip('0')  # strip zeros to right of decimal
        out = out.rstrip('.')  # and decimal place when not needed
    if valoff != 0:
        out += ("e{:d}").format(valoff) # add an exponent, when needed
    return out
    
###############################################################################
##### Protein validation - "ERRATV2" analysis
###############################################################################

def validProtein(Phase,old):
    
    def sumintact(intact):
        return {'CC':intact['CC'],'NN':intact['NN'],'OO':intact['OO'],
        'CN':(intact['CN']+intact['NC']),'CO':(intact['CO']+intact['OC']),
        'NO':(intact['NO']+intact['ON'])}
        
    resNames = ['ALA','ARG','ASN','ASP','CYS','GLN','GLU','GLY','HIS','ILE',
        'LEU','LYS','MET','PHE','PRO','SER','THR','TRP','TYR','VAL','MSE']
# data from errat.f
    b1_old = np.array([ 
        [1154.343,  600.213, 1051.018, 1132.885,  960.738],
        [600.213, 1286.818, 1282.042,  957.156,  612.789],
        [1051.018, 1282.042, 3519.471,  991.974, 1226.491],
        [1132.885,  957.156,  991.974, 1798.672,  820.355],
        [960.738,  612.789, 1226.491,  820.355, 2428.966]
        ])
    avg_old = np.array([ 0.225, 0.281, 0.071, 0.237, 0.044])    #Table 1 3.5A Obsd. Fr. p 1513
# data taken from erratv2.ccp
    b1 = np.array([
          [5040.279078850848200,	3408.805141583649400,	4152.904423767300600,	4236.200004171890200,	5054.781210204625500],	
          [3408.805141583648900,	8491.906094010220800,	5958.881777877950300,	1521.387352718486200,	4304.078200827221700],	
          [4152.904423767301500,	5958.881777877952100,	7637.167089335050100,	6620.715738223072500,	5287.691183798410700],	
          [4236.200004171890200,	1521.387352718486200,	6620.715738223072500,	18368.343774298410000,	4050.797811118806700],	
          [5054.781210204625500,	4304.078200827220800,	5287.691183798409800,	4050.797811118806700,	6666.856740479164700]])
    avg = np.array([0.192765509919262, 0.195575208778518, 0.275322406824210, 0.059102357035642, 0.233154192767480])
    General = Phase['General']
    Amat,Bmat = G2lat.cell2AB(General['Cell'][1:7])
    cx,ct,cs,cia = General['AtomPtrs']
    Atoms = Phase['Atoms']
    cartAtoms = []
    xyzmin = 999.*np.ones(3)
    xyzmax = -999.*np.ones(3)
    #select residue atoms,S,Se --> O make cartesian
    for atom in Atoms:
        if atom[1] in resNames:
            cartAtoms.append(atom[:cx+3])
            if atom[4].strip() in ['S','Se']:
                if not old:
                    continue        #S,Se skipped for erratv2?
                cartAtoms[-1][3] = 'Os'
                cartAtoms[-1][4] = 'O'
            cartAtoms[-1][cx:cx+3] = np.inner(Amat,cartAtoms[-1][cx:cx+3])
            cartAtoms[-1].append(atom[cia+8])
    XYZ = np.array([atom[cx:cx+3] for atom in cartAtoms])
    xyzmin = np.array([np.min(XYZ.T[i]) for i in [0,1,2]])
    xyzmax = np.array([np.max(XYZ.T[i]) for i in [0,1,2]])
    nbox = list(np.array(np.ceil((xyzmax-xyzmin)/4.),dtype=int))+[15,]
    Boxes = np.zeros(nbox,dtype=int)
    iBox = np.array([np.trunc((XYZ.T[i]-xyzmin[i])/4.) for i in [0,1,2]],dtype=int).T
    for ib,box in enumerate(iBox):  #put in a try for too many atoms in box (IndexError)?
        try:
            Boxes[box[0],box[1],box[2],0] += 1
            Boxes[box[0],box[1],box[2],Boxes[box[0],box[1],box[2],0]] = ib
        except IndexError:
            G2fil.G2Print('Error: too many atoms in box' )
            continue
    #Box content checks with errat.f $ erratv2.cpp ibox1 arrays
    indices = (-1,0,1)
    Units = np.array([[h,k,l] for h in indices for k in indices for l in indices]) 
    dsmax = 3.75**2
    if old:
        dsmax = 3.5**2
    chains = []
    resIntAct = []
    chainIntAct = []
    res = []
    resNames = []
    resIDs = {}
    resname = []
    resID = {}
    newChain = True
    intact = {'CC':0,'CN':0,'CO':0,'NN':0,'NO':0,'OO':0,'NC':0,'OC':0,'ON':0}
    for ia,atom in enumerate(cartAtoms):
        jntact = {'CC':0,'CN':0,'CO':0,'NN':0,'NO':0,'OO':0,'NC':0,'OC':0,'ON':0}
        if atom[2] not in chains:   #get chain id & save residue sequence from last chain
            chains.append(atom[2])
            if len(resIntAct):
                resIntAct.append(sumintact(intact))
                chainIntAct.append(resIntAct)
                resNames += resname
                resIDs.update(resID)
                res = []
                resname = []
                resID = {}
                resIntAct = []
                intact = {'CC':0,'CN':0,'CO':0,'NN':0,'NO':0,'OO':0,'NC':0,'OC':0,'ON':0}
                newChain = True
        if atom[0] not in res:  #new residue, get residue no.
            if res and int(res[-1]) != int(atom[0])-1:  #a gap in chain - not new chain
                intact = {'CC':0,'CN':0,'CO':0,'NN':0,'NO':0,'OO':0,'NC':0,'OC':0,'ON':0}
                ires = int(res[-1])
                for i in range(int(atom[0])-ires-1):
                    res.append(str(ires+i+1))
                    resname.append('')
                    resIntAct.append(sumintact(intact))
            res.append(atom[0])
            name = '%s-%s%s'%(atom[2],atom[0],atom[1])
            resname.append(name)
            resID[name] = atom[-1]
            if not newChain:
                resIntAct.append(sumintact(intact))
            intact = {'CC':0,'CN':0,'CO':0,'NN':0,'NO':0,'OO':0,'NC':0,'OC':0,'ON':0}
            newChain = False
        ibox = iBox[ia]         #box location of atom
        tgts = []
        for unit in Units:      #assemble list of all possible target atoms
            jbox = ibox+unit
            if np.all(jbox>=0) and np.all((jbox-nbox[:3])<0):                
                tgts += list(Boxes[jbox[0],jbox[1],jbox[2]])
        tgts = list(set(tgts))
        tgts = [tgt for tgt in tgts if atom[:3] != cartAtoms[tgt][:3]]    #exclude same residue
        tgts = [tgt for tgt in tgts if np.sum((XYZ[ia]-XYZ[tgt])**2) < dsmax]
        ires = int(atom[0])
        if old:
            if atom[3].strip() == 'C':
                tgts = [tgt for tgt in tgts if not (cartAtoms[tgt][3].strip() == 'N' and int(cartAtoms[tgt][0]) in [ires-1,ires+1])]
            elif atom[3].strip() == 'N':
                tgts = [tgt for tgt in tgts if not (cartAtoms[tgt][3].strip() in ['C','CA'] and int(cartAtoms[tgt][0]) in [ires-1,ires+1])]
            elif atom[3].strip() == 'CA':
                tgts = [tgt for tgt in tgts if not (cartAtoms[tgt][3].strip() == 'N' and int(cartAtoms[tgt][0]) in [ires-1,ires+1])]
        else:
            tgts = [tgt for tgt in tgts if not int(cartAtoms[tgt][0]) in [ires+1,ires+2,ires+3,ires+4,ires+5,ires+6,ires+7,ires+8]]
            if atom[3].strip() == 'C':
                tgts = [tgt for tgt in tgts if not (cartAtoms[tgt][3].strip() == 'N' and int(cartAtoms[tgt][0]) == ires+1)]
            elif atom[3].strip() == 'N':
                tgts = [tgt for tgt in tgts if not (cartAtoms[tgt][3].strip() == 'C' and int(cartAtoms[tgt][0]) == ires-1)]
        for tgt in tgts:
            dsqt = np.sqrt(np.sum((XYZ[ia]-XYZ[tgt])**2))
            mult = 1.0
            if dsqt > 3.25 and not old:
                mult = 2.*(3.75-dsqt)
            intype = atom[4].strip()+cartAtoms[tgt][4].strip()
            if 'S' not in intype:
                intact[intype] += mult
                jntact[intype] += mult
#        print ia,atom[0]+atom[1]+atom[3],tgts,jntact['CC'],jntact['CN']+jntact['NC'],jntact['CO']+jntact['OC'],jntact['NN'],jntact['NO']+jntact['ON']
    resNames += resname
    resIDs.update(resID)
    resIntAct.append(sumintact(intact))
    chainIntAct.append(resIntAct)
    chainProb = []
    for ich,chn in enumerate(chains):
        IntAct = chainIntAct[ich]
        nRes = len(IntAct)
        Probs = [0.,0.,0.,0.]   #skip 1st 4 residues in chain
        for i in range(4,nRes-4):
            if resNames[i]:
                mtrx = np.zeros(5)
                summ = 0.
                for j in range(i-4,i+5):
                    summ += np.sum(np.array(list(IntAct[j].values())))
                    if old:
                        mtrx[0] += IntAct[j]['CC']
                        mtrx[1] += IntAct[j]['CO']
                        mtrx[2] += IntAct[j]['NN']
                        mtrx[3] += IntAct[j]['NO']
                        mtrx[4] += IntAct[j]['OO']
                    else:
                        mtrx[0] += IntAct[j]['CC']
                        mtrx[1] += IntAct[j]['CN']
                        mtrx[2] += IntAct[j]['CO']
                        mtrx[3] += IntAct[j]['NN']
                        mtrx[4] += IntAct[j]['NO']
                mtrx /= summ
    #            print i+1,mtrx*summ
                if old:
                    mtrx -= avg_old
                    prob = np.inner(np.inner(mtrx,b1_old),mtrx)
                else:
                    mtrx -= avg
                    prob = np.inner(np.inner(mtrx,b1),mtrx)
            else:       #skip the gaps
                prob = 0.0
            Probs.append(prob)
        Probs += 4*[0.,]        #skip last 4 residues in chain
        chainProb += Probs
    return resNames,chainProb,resIDs
    
################################################################################
##### Texture fitting stuff
################################################################################

def FitTexture(General,Gangls,refData,keyList,pgbar):
    import pytexture as ptx
    ptx.pyqlmninit()            #initialize fortran arrays for spherical harmonics
    
    def printSpHarm(textureData,SHtextureSig):
        print ('\n Spherical harmonics texture: Order:' + str(textureData['Order']))
        names = ['omega','chi','phi']
        namstr = '  names :'
        ptstr =  '  values:'
        sigstr = '  esds  :'
        for name in names:
            namstr += '%12s'%('Sample '+name)
            ptstr += '%12.3f'%(textureData['Sample '+name][1])
            if 'Sample '+name in SHtextureSig:
                sigstr += '%12.3f'%(SHtextureSig['Sample '+name])
            else:
                sigstr += 12*' '
        print (namstr)
        print (ptstr)
        print (sigstr)
        print ('\n Texture coefficients:')
        SHcoeff = textureData['SH Coeff'][1]
        SHkeys = list(SHcoeff.keys())
        nCoeff = len(SHcoeff)
        nBlock = nCoeff//10+1
        iBeg = 0
        iFin = min(iBeg+10,nCoeff)
        for block in range(nBlock):
            namstr = '  names :'
            ptstr =  '  values:'
            sigstr = '  esds  :'
            for name in SHkeys[iBeg:iFin]:
                if 'C' in name:
                    namstr += '%12s'%(name)
                    ptstr += '%12.3f'%(SHcoeff[name])
                    if name in SHtextureSig:
                        sigstr += '%12.3f'%(SHtextureSig[name])
                    else:
                        sigstr += 12*' '
            print (namstr)
            print (ptstr)
            print (sigstr)
            iBeg += 10
            iFin = min(iBeg+10,nCoeff)
            
    def Dict2Values(parmdict, varylist):
        '''Use before call to leastsq to setup list of values for the parameters 
        in parmdict, as selected by key in varylist'''
        return [parmdict[key] for key in varylist] 
        
    def Values2Dict(parmdict, varylist, values):
        ''' Use after call to leastsq to update the parameter dictionary with 
        values corresponding to keys in varylist'''
        parmdict.update(list(zip(varylist,values)))
        
    def errSpHarm(values,SGData,cell,Gangls,shModel,refData,parmDict,varyList,pgbar):
        parmDict.update(list(zip(varyList,values)))
        Mat = np.empty(0)
        sumObs = 0
        Sangls = [parmDict['Sample '+'omega'],parmDict['Sample '+'chi'],parmDict['Sample '+'phi']]
        for hist in Gangls.keys():
            Refs = refData[hist]
            Refs[:,5] = np.where(Refs[:,5]>0.,Refs[:,5],0.)
            wt = 1./np.sqrt(np.fmax(Refs[:,4],.25))
#            wt = 1./np.max(Refs[:,4],.25)
            sumObs += np.sum(wt*Refs[:,5])
            Refs[:,6] = 1.
            H = Refs[:,:3]
            phi,beta = G2lat.CrsAng(H,cell,SGData)
            psi,gam,x,x = G2lat.SamAng(Refs[:,3]/2.,Gangls[hist],Sangls,False) #assume not Bragg-Brentano!
            for item in parmDict:
                if 'C' in item:
                    L,M,N = eval(item.strip('C'))
                    Kcl = G2lat.GetKcl(L,N,SGData['SGLaue'],phi,beta)
                    Ksl,x,x = G2lat.GetKsl(L,M,shModel,psi,gam)
                    Lnorm = G2lat.Lnorm(L)
                    Refs[:,6] += parmDict[item]*Lnorm*Kcl*Ksl
            mat = wt*(Refs[:,5]-Refs[:,6])
            Mat = np.concatenate((Mat,mat))
        sumD = np.sum(np.abs(Mat))
        R = min(100.,100.*sumD/sumObs)
        pgbar.Update(R,newmsg='Residual = %5.2f'%(R))
        print (' Residual: %.3f%%'%(R))
        return Mat
        
    def dervSpHarm(values,SGData,cell,Gangls,shModel,refData,parmDict,varyList,pgbar):
        Mat = np.empty(0)
        Sangls = [parmDict['Sample omega'],parmDict['Sample chi'],parmDict['Sample phi']]
        for hist in Gangls.keys():
            mat = np.zeros((len(varyList),len(refData[hist])))
            Refs = refData[hist]
            H = Refs[:,:3]
            wt = 1./np.sqrt(np.fmax(Refs[:,4],.25))
#            wt = 1./np.max(Refs[:,4],.25)
            phi,beta = G2lat.CrsAng(H,cell,SGData)
            psi,gam,dPdA,dGdA = G2lat.SamAng(Refs[:,3]/2.,Gangls[hist],Sangls,False) #assume not Bragg-Brentano!
            for j,item in enumerate(varyList):
                if 'C' in item:
                    L,M,N = eval(item.strip('C'))
                    Kcl = G2lat.GetKcl(L,N,SGData['SGLaue'],phi,beta)
                    Ksl,dKdp,dKdg = G2lat.GetKsl(L,M,shModel,psi,gam)
                    Lnorm = G2lat.Lnorm(L)
                    mat[j] = -wt*Lnorm*Kcl*Ksl
                    for k,itema in enumerate(['Sample omega','Sample chi','Sample phi']):
                        try:
                            l = varyList.index(itema)
                            mat[l] -= parmDict[item]*wt*Lnorm*Kcl*(dKdp*dPdA[k]+dKdg*dGdA[k])
                        except ValueError:
                            pass
            if len(Mat):
                Mat = np.concatenate((Mat,mat.T))
            else:
                Mat = mat.T
        print ('deriv')
        return Mat

    print (' Fit texture for '+General['Name'])
    SGData = General['SGData']
    cell = General['Cell'][1:7]
    Texture = General['SH Texture']
    if not Texture['Order']:
        return 'No spherical harmonics coefficients'
    varyList = []
    parmDict = copy.copy(Texture['SH Coeff'][1])
    for item in ['Sample omega','Sample chi','Sample phi']:
        parmDict[item] = Texture[item][1]
        if Texture[item][0]:
            varyList.append(item)
    if Texture['SH Coeff'][0]:
        varyList += list(Texture['SH Coeff'][1].keys())
    while True:
        begin = time.time()
        values =  np.array(Dict2Values(parmDict, varyList))
        result = so.leastsq(errSpHarm,values,Dfun=dervSpHarm,full_output=True,ftol=1.e-6,
            args=(SGData,cell,Gangls,Texture['Model'],refData,parmDict,varyList,pgbar))
        ncyc = int(result[2]['nfev']//2)
        if ncyc:
            runtime = time.time()-begin    
            chisq = np.sum(result[2]['fvec']**2)
            Values2Dict(parmDict, varyList, result[0])
            GOF = chisq/(len(result[2]['fvec'])-len(varyList))       #reduced chi^2
            G2fil.G2Print ('Number of function calls: %d Number of observations: %d Number of parameters: %d'%(result[2]['nfev'],len(result[2]['fvec']),len(varyList)))
            G2fil.G2Print ('refinement time = %8.3fs, %8.3fs/cycle'%(runtime,runtime/ncyc))
            try:
                sig = np.sqrt(np.diag(result[1])*GOF)
                if np.any(np.isnan(sig)):
                    G2fil.G2Print ('*** Least squares aborted - some invalid esds possible ***', mode='error')
                break                   #refinement succeeded - finish up!
            except ValueError:          #result[1] is None on singular matrix
                G2fil.G2Print ('**** Refinement failed - singular matrix ****', mode='error')
                return None
        else:
            break
    
    if ncyc:
        for parm in parmDict:
            if 'C' in parm:
                Texture['SH Coeff'][1][parm] = parmDict[parm]
            else:
                Texture[parm][1] = parmDict[parm]  
        sigDict = dict(zip(varyList,sig))
        printSpHarm(Texture,sigDict)
        
    return None
    
################################################################################
##### Fourier & charge flip stuff
################################################################################

def adjHKLmax(SGData,Hmax):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    if SGData['SGLaue'] in ['3','3m1','31m','6/m','6/mmm']:
        Hmax[0] = int(math.ceil(Hmax[0]/6.))*6
        Hmax[1] = int(math.ceil(Hmax[1]/6.))*6
        Hmax[2] = int(math.ceil(Hmax[2]/4.))*4
    else:
        Hmax[0] = int(math.ceil(Hmax[0]/4.))*4
        Hmax[1] = int(math.ceil(Hmax[1]/4.))*4
        Hmax[2] = int(math.ceil(Hmax[2]/4.))*4

def OmitMap(data,reflDict,pgbar=None):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    generalData = data['General']
    if not generalData['Map']['MapType']:
        G2fil.G2Print ('**** ERROR - Fourier map not defined')
        return
    mapData = generalData['Map']
    dmin = mapData['GridStep']*2.
    SGData = generalData['SGData']
    SGMT = np.array([ops[0].T for ops in SGData['SGOps']])
    SGT = np.array([ops[1] for ops in SGData['SGOps']])
    cell = generalData['Cell'][1:8]        
    A = G2lat.cell2A(cell[:6])
    Hmax = np.asarray(G2lat.getHKLmax(dmin,SGData,A),dtype='i')+1
    adjHKLmax(SGData,Hmax)
    Fhkl = np.zeros(shape=2*Hmax,dtype='c16')
    time0 = time.time()
    for iref,ref in enumerate(reflDict['RefList']):
        if ref[4] >= dmin:
            Fosq,Fcsq,ph = ref[8:11]
            Uniq = np.inner(ref[:3],SGMT)
            Phi = np.inner(ref[:3],SGT)
            for i,hkl in enumerate(Uniq):        #uses uniq
                hkl = np.asarray(hkl,dtype='i')
                dp = 360.*Phi[i]                #and phi
                a = cosd(ph+dp)
                b = sind(ph+dp)
                phasep = complex(a,b)
                phasem = complex(a,-b)
                if '2Fo-Fc' in mapData['MapType']:
                    F = 2.*np.sqrt(Fosq)-np.sqrt(Fcsq)
                else:
                    F = np.sqrt(Fosq)
                h,k,l = hkl+Hmax
                Fhkl[h,k,l] = F*phasep
                h,k,l = -hkl+Hmax
                Fhkl[h,k,l] = F*phasem
    rho0 = fft.fftn(fft.fftshift(Fhkl))/cell[6]
    M = np.mgrid[0:4,0:4,0:4]
    blkIds = np.array(list(zip(M[0].flatten(),M[1].flatten(),M[2].flatten())))
    iBeg = blkIds*rho0.shape//4
    iFin = (blkIds+1)*rho0.shape//4
    rho_omit = np.zeros_like(rho0)
    nBlk = 0
    for iB,iF in zip(iBeg,iFin):
        rho1 = np.copy(rho0)
        rho1[iB[0]:iF[0],iB[1]:iF[1],iB[2]:iF[2]] = 0.
        Fnew = fft.ifftshift(fft.ifftn(rho1))
        Fnew = np.where(Fnew,Fnew,1.0)           #avoid divide by zero
        phase = Fnew/np.absolute(Fnew)
        OFhkl = np.absolute(Fhkl)*phase
        rho1 = np.real(fft.fftn(fft.fftshift(OFhkl)))*(1.+0j)
        rho_omit[iB[0]:iF[0],iB[1]:iF[1],iB[2]:iF[2]] = np.copy(rho1[iB[0]:iF[0],iB[1]:iF[1],iB[2]:iF[2]])
        nBlk += 1
        pgbar.Update(nBlk)
    mapData['rho'] = np.real(rho_omit)/cell[6]
    mapData['rhoMax'] = max(np.max(mapData['rho']),-np.min(mapData['rho']))
    mapData['minmax'] = [np.max(mapData['rho']),np.min(mapData['rho'])]
    G2fil.G2Print ('Omit map time: %.4f no. elements: %d dimensions: %s'%(time.time()-time0,Fhkl.size,str(Fhkl.shape)))
    return mapData
    
def FourierMap(data,reflDict):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    generalData = data['General']
    mapData = generalData['Map']
    dmin = mapData['GridStep']*2.
    SGData = generalData['SGData']
    SGMT = np.array([ops[0].T for ops in SGData['SGOps']])
    SGT = np.array([ops[1] for ops in SGData['SGOps']])
    cell = generalData['Cell'][1:8]        
    A = G2lat.cell2A(cell[:6])
    Hmax = np.asarray(G2lat.getHKLmax(dmin,SGData,A),dtype='i')+1
    adjHKLmax(SGData,Hmax)
    Fhkl = np.zeros(shape=2*Hmax,dtype='c16')
#    Fhkl[0,0,0] = generalData['F000X']
    time0 = time.time()
    for iref,ref in enumerate(reflDict['RefList']):
        if ref[4] > dmin:
            Fosq,Fcsq,ph = ref[8:11]
            Uniq = np.inner(ref[:3],SGMT)
            Phi = np.inner(ref[:3],SGT)
            for i,hkl in enumerate(Uniq):        #uses uniq
                hkl = np.asarray(hkl,dtype='i')
                dp = 360.*Phi[i]                #and phi
                a = cosd(ph+dp)
                b = sind(ph+dp)
                phasep = complex(a,b)
                phasem = complex(a,-b)
                if 'Fobs' in mapData['MapType']:
                    F = np.where(Fosq>0.,np.sqrt(Fosq),0.)
                    h,k,l = hkl+Hmax
                    Fhkl[h,k,l] = F*phasep
                    h,k,l = -hkl+Hmax
                    Fhkl[h,k,l] = F*phasem
                elif 'Fcalc' in mapData['MapType']:
                    F = np.sqrt(Fcsq)
                    h,k,l = hkl+Hmax
                    Fhkl[h,k,l] = F*phasep
                    h,k,l = -hkl+Hmax
                    Fhkl[h,k,l] = F*phasem
                elif 'delt-F' in mapData['MapType']:
                    dF = np.where(Fosq>0.,np.sqrt(Fosq),0.)-np.sqrt(Fcsq)
                    h,k,l = hkl+Hmax
                    Fhkl[h,k,l] = dF*phasep
                    h,k,l = -hkl+Hmax
                    Fhkl[h,k,l] = dF*phasem
                elif '2*Fo-Fc' in mapData['MapType']:
                    F = 2.*np.where(Fosq>0.,np.sqrt(Fosq),0.)-np.sqrt(Fcsq)
                    h,k,l = hkl+Hmax
                    Fhkl[h,k,l] = F*phasep
                    h,k,l = -hkl+Hmax
                    Fhkl[h,k,l] = F*phasem
                elif 'Patterson' in mapData['MapType']:
                    h,k,l = hkl+Hmax
                    Fhkl[h,k,l] = complex(Fosq,0.)
                    h,k,l = -hkl+Hmax
                    Fhkl[h,k,l] = complex(Fosq,0.)
    rho = fft.fftn(fft.fftshift(Fhkl))/cell[6]
    G2fil.G2Print ('Fourier map time: %.4f no. elements: %d dimensions: %s'%(time.time()-time0,Fhkl.size,str(Fhkl.shape)))
    mapData['Type'] = reflDict['Type']
    mapData['rho'] = np.real(rho)
    mapData['rhoMax'] = max(np.max(mapData['rho']),-np.min(mapData['rho']))
    mapData['minmax'] = [np.max(mapData['rho']),np.min(mapData['rho'])]
    
def Fourier4DMap(data,reflDict):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    generalData = data['General']
    map4DData = generalData['4DmapData']
    mapData = generalData['Map']
    dmin = mapData['GridStep']*2.
    SGData = generalData['SGData']
    SSGData = generalData['SSGData']
    SSGMT = np.array([ops[0].T for ops in SSGData['SSGOps']])
    SSGT = np.array([ops[1] for ops in SSGData['SSGOps']])
    cell = generalData['Cell'][1:8]        
    A = G2lat.cell2A(cell[:6])
    maxM = 4
    Hmax = G2lat.getHKLmax(dmin,SGData,A)+[maxM,]
    adjHKLmax(SGData,Hmax)
    Hmax = np.asarray(Hmax,dtype='i')+1
    Fhkl = np.zeros(shape=2*Hmax,dtype='c16')
    time0 = time.time()
    for iref,ref in enumerate(reflDict['RefList']):
        if ref[5] > dmin:
            Fosq,Fcsq,ph = ref[9:12]
            Fosq = np.where(Fosq>0.,Fosq,0.)    #can't use Fo^2 < 0
            Uniq = np.inner(ref[:4],SSGMT)
            Phi = np.inner(ref[:4],SSGT)
            for i,hkl in enumerate(Uniq):        #uses uniq
                hkl = np.asarray(hkl,dtype='i')
                dp = 360.*Phi[i]                #and phi
                a = cosd(ph+dp)
                b = sind(ph+dp)
                phasep = complex(a,b)
                phasem = complex(a,-b)
                if 'Fobs' in mapData['MapType']:
                    F = np.sqrt(Fosq)
                    h,k,l,m = hkl+Hmax
                    Fhkl[h,k,l,m] = F*phasep
                    h,k,l,m = -hkl+Hmax
                    Fhkl[h,k,l,m] = F*phasem
                elif 'Fcalc' in mapData['MapType']:
                    F = np.sqrt(Fcsq)
                    h,k,l,m = hkl+Hmax
                    Fhkl[h,k,l,m] = F*phasep
                    h,k,l,m = -hkl+Hmax
                    Fhkl[h,k,l,m] = F*phasem                    
                elif 'delt-F' in mapData['MapType']:
                    dF = np.sqrt(Fosq)-np.sqrt(Fcsq)
                    h,k,l,m = hkl+Hmax
                    Fhkl[h,k,l,m] = dF*phasep
                    h,k,l,m = -hkl+Hmax
                    Fhkl[h,k,l,m] = dF*phasem
    SSrho = fft.fftn(fft.fftshift(Fhkl))/cell[6]          #4D map 
    rho = fft.fftn(fft.fftshift(Fhkl[:,:,:,maxM+1]))/cell[6]    #3D map
    map4DData['rho'] = np.real(SSrho)
    map4DData['rhoMax'] = max(np.max(map4DData['rho']),-np.min(map4DData['rho']))
    map4DData['minmax'] = [np.max(map4DData['rho']),np.min(map4DData['rho'])]
    map4DData['Type'] = reflDict['Type']
    mapData['Type'] = reflDict['Type']
    mapData['rho'] = np.real(rho)
    mapData['rhoMax'] = max(np.max(mapData['rho']),-np.min(mapData['rho']))
    mapData['minmax'] = [np.max(mapData['rho']),np.min(mapData['rho'])]
    G2fil.G2Print ('Fourier map time: %.4f no. elements: %d dimensions: %s'%(time.time()-time0,Fhkl.size,str(Fhkl.shape)))

# map printing for testing purposes
def printRho(SGLaue,rho,rhoMax):                          
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    dim = len(rho.shape)
    if dim == 2:
        ix,jy = rho.shape
        for j in range(jy):
            line = ''
            if SGLaue in ['3','3m1','31m','6/m','6/mmm']:
                line += (jy-j)*'  '
            for i in range(ix):
                r = int(100*rho[i,j]/rhoMax)
                line += '%4d'%(r)
            print (line+'\n')
    else:
        ix,jy,kz = rho.shape
        for k in range(kz):
            print ('k = %d'%k)
            for j in range(jy):
                line = ''
                if SGLaue in ['3','3m1','31m','6/m','6/mmm']:
                    line += (jy-j)*'  '
                for i in range(ix):
                    r = int(100*rho[i,j,k]/rhoMax)
                    line += '%4d'%(r)
                print (line+'\n')
## keep this
                
def findOffset(SGData,A,Fhkl):    
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    if SGData['SpGrp'] == 'P 1':
        return [0,0,0]    
    hklShape = Fhkl.shape
    hklHalf = np.array(hklShape)/2
    sortHKL = np.argsort(Fhkl.flatten())
    Fdict = {}
    for hkl in sortHKL:
        HKL = np.unravel_index(hkl,hklShape)
        F = Fhkl[HKL[0]][HKL[1]][HKL[2]]
        if F == 0.:
            break
        Fdict['%.6f'%(np.absolute(F))] = hkl
    Flist = np.flipud(np.sort(list(Fdict.keys())))
    F = str(1.e6)
    i = 0
    DH = []
    Dphi = []
    Hmax = 2*np.asarray(G2lat.getHKLmax(3.5,SGData,A),dtype='i')
    for F in Flist:
        hkl = np.unravel_index(Fdict[F],hklShape)
        if np.any(np.abs(hkl-hklHalf)-Hmax > 0):
            continue
        iabsnt,mulp,Uniq,Phi = G2spc.GenHKLf(list(hkl-hklHalf),SGData)
        Uniq = np.array(Uniq,dtype='i')
        Phi = np.array(Phi)
        Uniq = np.concatenate((Uniq,-Uniq))+hklHalf         # put in Friedel pairs & make as index to Farray
        Phi = np.concatenate((Phi,-Phi))                      # and their phase shifts
        Fh0 = Fhkl[hkl[0],hkl[1],hkl[2]]
        ang0 = np.angle(Fh0,deg=True)/360.
        for H,phi in list(zip(Uniq,Phi))[1:]:
            ang = (np.angle(Fhkl[int(H[0]),int(H[1]),int(H[2])],deg=True)/360.-phi)
            dH = H-hkl
            dang = ang-ang0
            DH.append(dH)
            Dphi.append((dang+.5) % 1.0)
        if i > 20 or len(DH) > 30:
            break
        i += 1
    DH = np.array(DH)
    G2fil.G2Print (' map offset no.of terms: %d from %d reflections'%(len(DH),len(Flist)))
    Dphi = np.array(Dphi)
    steps = np.array(hklShape)
    X,Y,Z = np.mgrid[0:1:1./steps[0],0:1:1./steps[1],0:1:1./steps[2]]
    XYZ = np.array(list(zip(X.flatten(),Y.flatten(),Z.flatten())))
    Dang = (np.dot(XYZ,DH.T)+.5)%1.-Dphi
    Mmap = np.reshape(np.sum((Dang)**2,axis=1),newshape=steps)/len(DH)
    hist,bins = np.histogram(Mmap,bins=1000)
#    for i,item in enumerate(hist[:10]):
#        print item,bins[i]
    chisq = np.min(Mmap)
    DX = -np.array(np.unravel_index(np.argmin(Mmap),Mmap.shape))
    G2fil.G2Print (' map offset chi**2: %.3f, map offset: %d %d %d'%(chisq,DX[0],DX[1],DX[2]))
#    print (np.dot(DX,DH.T)+.5)%1.-Dphi
    return DX
    
def ChargeFlip(data,reflDict,pgbar):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    generalData = data['General']
    mapData = generalData['Map']
    flipData = generalData['Flip']
    FFtable = {}
    if 'None' not in flipData['Norm element']:
        normElem = flipData['Norm element'].upper()
        FFs = G2el.GetFormFactorCoeff(normElem.split('+')[0].split('-')[0])
        for ff in FFs:
            if ff['Symbol'] == normElem:
                FFtable.update(ff)
    dmin = flipData['GridStep']*2.
    SGData = generalData['SGData']
    SGMT = np.array([ops[0].T for ops in SGData['SGOps']])
    SGT = np.array([ops[1] for ops in SGData['SGOps']])
    cell = generalData['Cell'][1:8]        
    A = G2lat.cell2A(cell[:6])
    Vol = cell[6]
    im = 0
    if generalData['Modulated'] == True:
        im = 1
    Hmax = np.asarray(G2lat.getHKLmax(dmin,SGData,A),dtype='i')+1
    adjHKLmax(SGData,Hmax)
    Ehkl = np.zeros(shape=2*Hmax,dtype='c16')       #2X64bits per complex no.
    time0 = time.time()
    for iref,ref in enumerate(reflDict['RefList']):
        dsp = ref[4+im]
        if im and ref[3]:   #skip super lattice reflections - result is 3D projection
            continue
        if dsp > dmin:
            ff = 0.1*Vol    #est. no. atoms for ~10A**3/atom
            if FFtable:
                SQ = 0.25/dsp**2
                ff *= G2el.ScatFac(FFtable,SQ)[0]
            if ref[8+im] > 0.:         #use only +ve Fobs**2
                E = np.sqrt(ref[8+im])/ff
            else:
                E = 0.
            ph = ref[10]
            ph = rn.uniform(0.,360.)
            Uniq = np.inner(ref[:3],SGMT)
            Phi = np.inner(ref[:3],SGT)
            for i,hkl in enumerate(Uniq):        #uses uniq
                hkl = np.asarray(hkl,dtype='i')
                dp = 360.*Phi[i]                #and phi
                a = cosd(ph+dp)
                b = sind(ph+dp)
                phasep = complex(a,b)
                phasem = complex(a,-b)
                h,k,l = hkl+Hmax
                Ehkl[h,k,l] = E*phasep
                h,k,l = -hkl+Hmax
                Ehkl[h,k,l] = E*phasem
#    Ehkl[Hmax] = 0.00001           #this to preserve F[0,0,0]
    testHKL = np.array(flipData['testHKL'])+Hmax
    CEhkl = copy.copy(Ehkl)
    MEhkl = ma.array(Ehkl,mask=(Ehkl==0.0))
    Emask = ma.getmask(MEhkl)
    sumE = np.sum(ma.array(np.absolute(CEhkl),mask=Emask))
    Ncyc = 0
    old = np.seterr(all='raise')
    twophases = []
    while True:        
        CErho = np.real(fft.fftn(fft.fftshift(CEhkl)))*(1.+0j)
        CEsig = np.std(CErho)
        CFrho = np.where(np.real(CErho) >= flipData['k-factor']*CEsig,CErho,-CErho)
        CFrho = np.where(np.real(CErho) <= flipData['k-Max']*CEsig,CFrho,-CFrho)      #solves U atom problem!
        CFhkl = fft.ifftshift(fft.ifftn(CFrho))
        CFhkl = np.where(CFhkl,CFhkl,1.0)           #avoid divide by zero
        phase = CFhkl/np.absolute(CFhkl)
        twophases.append([np.angle(phase[h,k,l]) for h,k,l in testHKL])
        CEhkl = np.absolute(Ehkl)*phase
        Ncyc += 1
        sumCF = np.sum(ma.array(np.absolute(CFhkl),mask=Emask))
        DEhkl = np.absolute(np.absolute(Ehkl)/sumE-np.absolute(CFhkl)/sumCF)
        Rcf = min(100.,np.sum(ma.array(DEhkl,mask=Emask)*100.))
        if Rcf < 5.:
            break
        GoOn = pgbar.Update(Rcf,newmsg='%s%8.3f%s\n%s %d'%('Residual Rcf =',Rcf,'%','No.cycles = ',Ncyc))[0]
        if not GoOn or Ncyc > 10000:
            break
    np.seterr(**old)
    G2fil.G2Print (' Charge flip time: %.4f'%(time.time()-time0),'no. elements: %d'%(Ehkl.size))
    CErho = np.real(fft.fftn(fft.fftshift(CEhkl)))/10.  #? to get on same scale as e-map
    G2fil.G2Print (' No.cycles = %d Residual Rcf =%8.3f%s Map size: %s'%(Ncyc,Rcf,'%',str(CErho.shape)))
    roll = findOffset(SGData,A,CEhkl)               #CEhkl needs to be just the observed set, not the full set!
        
    mapData['Rcf'] = Rcf
    mapData['rho'] = np.roll(np.roll(np.roll(CErho,roll[0],axis=0),roll[1],axis=1),roll[2],axis=2)
    mapData['rhoMax'] = max(np.max(mapData['rho']),-np.min(mapData['rho']))
    mapData['minmax'] = [np.max(mapData['rho']),np.min(mapData['rho'])]
    mapData['Type'] = reflDict['Type']
    return mapData,twophases
    
def findSSOffset(SGData,SSGData,A,Fhklm):    
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    if SGData['SpGrp'] == 'P 1':
        return [0,0,0,0]    
    hklmShape = Fhklm.shape
    hklmHalf = np.array(hklmShape)/2
    sortHKLM = np.argsort(Fhklm.flatten())
    Fdict = {}
    for hklm in sortHKLM:
        HKLM = np.unravel_index(hklm,hklmShape)
        F = Fhklm[HKLM[0]][HKLM[1]][HKLM[2]][HKLM[3]]
        if F == 0.:
            break
        Fdict['%.6f'%(np.absolute(F))] = hklm
    Flist = np.flipud(np.sort(list(Fdict.keys())))
    F = str(1.e6)
    i = 0
    DH = []
    Dphi = []
    SSGMT = np.array([ops[0].T for ops in SSGData['SSGOps']])
    SSGT = np.array([ops[1] for ops in SSGData['SSGOps']])
    Hmax = 2*np.asarray(G2lat.getHKLmax(3.5,SGData,A),dtype='i')
    for F in Flist:
        hklm = np.unravel_index(Fdict[F],hklmShape)
        if np.any(np.abs(hklm-hklmHalf)[:3]-Hmax > 0):
            continue
        Uniq = np.inner(hklm-hklmHalf,SSGMT)
        Phi = np.inner(hklm-hklmHalf,SSGT)
        Uniq = np.concatenate((Uniq,-Uniq))+hklmHalf         # put in Friedel pairs & make as index to Farray
        Phi = np.concatenate((Phi,-Phi))                      # and their phase shifts
        Fh0 = Fhklm[hklm[0],hklm[1],hklm[2],hklm[3]]
        ang0 = np.angle(Fh0,deg=True)/360.
        for H,phi in list(zip(Uniq,Phi))[1:]:
            H = np.array(H,dtype=int)
            ang = (np.angle(Fhklm[H[0],H[1],H[2],H[3]],deg=True)/360.-phi)
            dH = H-hklm
            dang = ang-ang0
            DH.append(dH)
            Dphi.append((dang+.5) % 1.0)
        if i > 20 or len(DH) > 30:
            break
        i += 1
    DH = np.array(DH)
    G2fil.G2Print (' map offset no.of terms: %d from %d reflections'%(len(DH),len(Flist)))
    Dphi = np.array(Dphi)
    steps = np.array(hklmShape)
    X,Y,Z,T = np.mgrid[0:1:1./steps[0],0:1:1./steps[1],0:1:1./steps[2],0:1:1./steps[3]]
    XYZT = np.array(list(zip(X.flatten(),Y.flatten(),Z.flatten(),T.flatten())))
    Dang = (np.dot(XYZT,DH.T)+.5)%1.-Dphi
    Mmap = np.reshape(np.sum((Dang)**2,axis=1),newshape=steps)/len(DH)
    hist,bins = np.histogram(Mmap,bins=1000)
#    for i,item in enumerate(hist[:10]):
#        print item,bins[i]
    chisq = np.min(Mmap)
    DX = -np.array(np.unravel_index(np.argmin(Mmap),Mmap.shape))
    G2fil.G2Print (' map offset chi**2: %.3f, map offset: %d %d %d %d'%(chisq,DX[0],DX[1],DX[2],DX[3]))
#    print (np.dot(DX,DH.T)+.5)%1.-Dphi
    return DX
    
def SSChargeFlip(data,reflDict,pgbar):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    
    '''
    generalData = data['General']
    mapData = generalData['Map']
    map4DData = {}
    flipData = generalData['Flip']
    FFtable = {}
    if 'None' not in flipData['Norm element']:
        normElem = flipData['Norm element'].upper()
        FFs = G2el.GetFormFactorCoeff(normElem.split('+')[0].split('-')[0])
        for ff in FFs:
            if ff['Symbol'] == normElem:
                FFtable.update(ff)
    dmin = flipData['GridStep']*2.
    SGData = generalData['SGData']
    SSGData = generalData['SSGData']
    SSGMT = np.array([ops[0].T for ops in SSGData['SSGOps']])
    SSGT = np.array([ops[1] for ops in SSGData['SSGOps']])
    cell = generalData['Cell'][1:8]        
    A = G2lat.cell2A(cell[:6])
    Vol = cell[6]
    maxM = 4
    Hmax = np.asarray(G2lat.getHKLmax(dmin,SGData,A)+[maxM,],dtype='i')+1
    adjHKLmax(SGData,Hmax)
    Ehkl = np.zeros(shape=2*Hmax,dtype='c16')       #2X64bits per complex no.
    time0 = time.time()
    for iref,ref in enumerate(reflDict['RefList']):
        dsp = ref[5]
        if dsp > dmin:
            ff = 0.1*Vol    #est. no. atoms for ~10A**3/atom
            if FFtable:
                SQ = 0.25/dsp**2
                ff *= G2el.ScatFac(FFtable,SQ)[0]
            if ref[9] > 0.:         #use only +ve Fobs**2
                E = np.sqrt(ref[9])/ff
            else:
                E = 0.
            ph = ref[11]
            ph = rn.uniform(0.,360.)
            Uniq = np.inner(ref[:4],SSGMT)
            Phi = np.inner(ref[:4],SSGT)
            for i,hklm in enumerate(Uniq):        #uses uniq
                hklm = np.asarray(hklm,dtype='i')
                dp = 360.*Phi[i]                #and phi
                a = cosd(ph+dp)
                b = sind(ph+dp)
                phasep = complex(a,b)
                phasem = complex(a,-b)
                h,k,l,m = hklm+Hmax
                Ehkl[h,k,l,m] = E*phasep
                h,k,l,m = -hklm+Hmax       #Friedel pair refl.
                Ehkl[h,k,l,m] = E*phasem
#    Ehkl[Hmax] = 0.00001           #this to preserve F[0,0,0]
    CEhkl = copy.copy(Ehkl)
    MEhkl = ma.array(Ehkl,mask=(Ehkl==0.0))
    Emask = ma.getmask(MEhkl)
    sumE = np.sum(ma.array(np.absolute(CEhkl),mask=Emask))
    Ncyc = 0
    old = np.seterr(all='raise')
    while True:        
        CErho = np.real(fft.fftn(fft.fftshift(CEhkl)))*(1.+0j)
        CEsig = np.std(CErho)
        CFrho = np.where(np.real(CErho) >= flipData['k-factor']*CEsig,CErho,-CErho)
        CFrho = np.where(np.real(CErho) <= flipData['k-Max']*CEsig,CFrho,-CFrho)      #solves U atom problem!
        CFhkl = fft.ifftshift(fft.ifftn(CFrho))
        CFhkl = np.where(CFhkl,CFhkl,1.0)           #avoid divide by zero
        phase = CFhkl/np.absolute(CFhkl)
        CEhkl = np.absolute(Ehkl)*phase
        Ncyc += 1
        sumCF = np.sum(ma.array(np.absolute(CFhkl),mask=Emask))
        DEhkl = np.absolute(np.absolute(Ehkl)/sumE-np.absolute(CFhkl)/sumCF)
        Rcf = min(100.,np.sum(ma.array(DEhkl,mask=Emask)*100.))
        if Rcf < 5.:
            break
        GoOn = pgbar.Update(Rcf,newmsg='%s%8.3f%s\n%s %d'%('Residual Rcf =',Rcf,'%','No.cycles = ',Ncyc))[0]
        if not GoOn or Ncyc > 10000:
            break
    np.seterr(**old)
    G2fil.G2Print (' Charge flip time: %.4f no. elements: %d'%(time.time()-time0,Ehkl.size))
    CErho = np.real(fft.fftn(fft.fftshift(CEhkl[:,:,:,maxM+1])))/10.    #? to get on same scale as e-map
    SSrho = np.real(fft.fftn(fft.fftshift(CEhkl)))/10.                  #? ditto
    G2fil.G2Print (' No.cycles = %d Residual Rcf =%8.3f%s Map size: %s'%(Ncyc,Rcf,'%',str(CErho.shape)))
    roll = findSSOffset(SGData,SSGData,A,CEhkl)               #CEhkl needs to be just the observed set, not the full set!

    mapData['Rcf'] = Rcf
    mapData['rho'] = np.roll(np.roll(np.roll(CErho,roll[0],axis=0),roll[1],axis=1),roll[2],axis=2)
    mapData['rhoMax'] = max(np.max(mapData['rho']),-np.min(mapData['rho']))
    mapData['minmax'] = [np.max(mapData['rho']),np.min(mapData['rho'])]
    mapData['Type'] = reflDict['Type']

    map4DData['Rcf'] = Rcf
    map4DData['rho'] = np.real(np.roll(np.roll(np.roll(np.roll(SSrho,roll[0],axis=0),roll[1],axis=1),roll[2],axis=2),roll[3],axis=3))
    map4DData['rhoMax'] = max(np.max(map4DData['rho']),-np.min(map4DData['rho']))
    map4DData['minmax'] = [np.max(map4DData['rho']),np.min(map4DData['rho'])]
    map4DData['Type'] = reflDict['Type']
    return mapData,map4DData
    
def getRho(xyz,mapData):
    ''' get scattering density at a point by 8-point interpolation
    param xyz: coordinate to be probed
    param: mapData: dict of map data
    
    :returns: density at xyz
    '''
    rollMap = lambda rho,roll: np.roll(np.roll(np.roll(rho,roll[0],axis=0),roll[1],axis=1),roll[2],axis=2)
    if not len(mapData):
        return 0.0
    rho = copy.copy(mapData['rho'])     #don't mess up original
    if not len(rho):
        return 0.0
    mapShape = np.array(rho.shape)
    mapStep = 1./mapShape
    X = np.array(xyz)%1.    #get into unit cell
    I = np.array(X*mapShape,dtype='int')
    D = X-I*mapStep         #position inside map cell
    D12 = D[0]*D[1]
    D13 = D[0]*D[2]
    D23 = D[1]*D[2]
    D123 = np.prod(D)
    Rho = rollMap(rho,-I)    #shifts map so point is in corner
    R = Rho[0,0,0]*(1.-np.sum(D))+Rho[1,0,0]*D[0]+Rho[0,1,0]*D[1]+Rho[0,0,1]*D[2]+  \
        Rho[1,1,1]*D123+Rho[0,1,1]*(D23-D123)+Rho[1,0,1]*(D13-D123)+Rho[1,1,0]*(D12-D123)+  \
        Rho[0,0,0]*(D12+D13+D23-D123)-Rho[0,0,1]*(D13+D23-D123)-    \
        Rho[0,1,0]*(D23+D12-D123)-Rho[1,0,0]*(D13+D12-D123)    
    return R
       
def getRhos(XYZ,rho):
    ''' get scattering density at an array of point by 8-point interpolation
    this is faster than gerRho which is only used for single points. However, getRhos is
    replaced by scipy.ndimage.interpolation.map_coordinates which does a better job &  is just as fast.
    Thus, getRhos is unused in GSAS-II at this time.
    param xyz:  array coordinates to be probed Nx3
    param: rho: array copy of map (NB: don't use original!)
    
    :returns: density at xyz
    '''
    def getBoxes(rho,I):
        Rhos = np.zeros((2,2,2))
        Mx,My,Mz = rho.shape
        Ix,Iy,Iz = I
        Rhos = np.array([[[rho[Ix%Mx,Iy%My,Iz%Mz],rho[Ix%Mx,Iy%My,(Iz+1)%Mz]],
                          [rho[Ix%Mx,(Iy+1)%My,Iz%Mz],rho[Ix%Mx,(Iy+1)%My,(Iz+1)%Mz]]],
                        [[rho[(Ix+1)%Mx,Iy%My,Iz%Mz],rho[(Ix+1)%Mx,Iy%My,(Iz+1)%Mz]],
                          [rho[(Ix+1)%Mx,(Iy+1)%My,Iz%Mz],rho[(Ix+1)%Mx,(Iy+1)%My,(Iz+1)%Mz]]]])
        return Rhos
        
    Blk = 400     #400 doesn't seem to matter
    nBlk = len(XYZ)//Blk        #select Blk so this is an exact divide
    mapShape = np.array(rho.shape)
    mapStep = 1./mapShape
    X = XYZ%1.    #get into unit cell
    iBeg = 0
    R = np.zeros(len(XYZ))
#actually a lot faster!
    for iblk in range(nBlk):
        iFin = iBeg+Blk
        Xs = X[iBeg:iFin]
        I = np.array(np.rint(Xs*mapShape),dtype='int')
        Rhos = np.array([getBoxes(rho,i) for i in I])
        Ds = Xs-I*mapStep
        RIJs = Rhos[:,0,:2,:2]*(1.-Ds[:,0][:,nxs,nxs])
        RIs = RIJs[:,0]*(1.-Ds[:,1][:,nxs])+RIJs[:,1]*Ds[:,1][:,nxs]
        R[iBeg:iFin] = RIs[:,0]*(1.-Ds[:,2])+RIs[:,1]*Ds[:,2]
        iBeg += Blk
    return R
       
def SearchMap(generalData,drawingData,Neg=False):
    '''Does a search of a density map for peaks meeting the criterion of peak
    height is greater than mapData['cutOff']/100 of mapData['rhoMax'] where 
    mapData is data['General']['mapData']; the map is also in mapData.

    :param generalData: the phase data structure; includes the map
    :param drawingData: the drawing data structure
    :param Neg:  if True then search for negative peaks (i.e. H-atoms & neutron data)

    :returns: (peaks,mags,dzeros) where

        * peaks : ndarray
          x,y,z positions of the peaks found in the map
        * mags : ndarray
          the magnitudes of the peaks
        * dzeros : ndarray
          the distance of the peaks from  the unit cell origin
        * dcent : ndarray
          the distance of the peaks from  the unit cell center

    '''        
    rollMap = lambda rho,roll: np.roll(np.roll(np.roll(rho,roll[0],axis=0),roll[1],axis=1),roll[2],axis=2)
    
    norm = 1./(np.sqrt(3.)*np.sqrt(2.*np.pi)**3)
    
    def fixSpecialPos(xyz,SGData,Amat):
        equivs = G2spc.GenAtom(xyz,SGData,Move=True)
        X = []
        xyzs = [equiv[0] for equiv in equivs]
        for x in xyzs:
            if np.sqrt(np.sum(np.inner(Amat,xyz-x)**2,axis=0))<0.5:
                X.append(x)
        if len(X) > 1:
            return np.average(X,axis=0)
        else:
            return xyz
        
    def rhoCalc(parms,rX,rY,rZ,res,SGLaue):
        Mag,x0,y0,z0,sig = parms
        z = -((x0-rX)**2+(y0-rY)**2+(z0-rZ)**2)/(2.*sig**2)
#        return norm*Mag*np.exp(z)/(sig*res**3)     #not slower but some faults in LS
        return norm*Mag*(1.+z+z**2/2.)/(sig*res**3)
        
    def peakFunc(parms,rX,rY,rZ,rho,res,SGLaue):
        Mag,x0,y0,z0,sig = parms
        M = rho-rhoCalc(parms,rX,rY,rZ,res,SGLaue)
        return M
        
    def peakHess(parms,rX,rY,rZ,rho,res,SGLaue):
        Mag,x0,y0,z0,sig = parms
        dMdv = np.zeros(([5,]+list(rX.shape)))
        delt = .01
        for i in range(5):
            parms[i] -= delt
            rhoCm = rhoCalc(parms,rX,rY,rZ,res,SGLaue)
            parms[i] += 2.*delt
            rhoCp = rhoCalc(parms,rX,rY,rZ,res,SGLaue)
            parms[i] -= delt
            dMdv[i] = (rhoCp-rhoCm)/(2.*delt)
        rhoC = rhoCalc(parms,rX,rY,rZ,res,SGLaue)
        Vec = np.sum(np.sum(np.sum(dMdv*(rho-rhoC),axis=3),axis=2),axis=1)
        dMdv = np.reshape(dMdv,(5,rX.size))
        Hess = np.inner(dMdv,dMdv)
        
        return Vec,Hess
        
    SGData = generalData['SGData']
    Amat,Bmat = G2lat.cell2AB(generalData['Cell'][1:7])
    peaks = []
    mags = []
    dzeros = []
    dcent = []
    try:
        mapData = generalData['Map']
        contLevel = mapData['cutOff']*mapData['rhoMax']/100.
        if Neg:
            rho = -copy.copy(mapData['rho'])     #flip +/-
        else:
            rho = copy.copy(mapData['rho'])     #don't mess up original
        mapHalf = np.array(rho.shape)/2
        res = mapData['GridStep']*2.
        incre = np.array(rho.shape,dtype=np.float)
        step = max(1.0,1./res)+1
        steps = np.array((3*[step,]),dtype='int32')
    except KeyError:
        G2fil.G2Print ('**** ERROR - Fourier map not defined')
        return peaks,mags
    rhoMask = ma.array(rho,mask=(rho<contLevel))
    indices = (-1,0,1)
    rolls = np.array([[h,k,l] for h in indices for k in indices for l in indices])
    for roll in rolls:
        if np.any(roll):
            rhoMask = ma.array(rhoMask,mask=(rhoMask-rollMap(rho,roll)<=0.))
    indx = np.transpose(rhoMask.nonzero())
    peaks = indx/incre
    mags = rhoMask[rhoMask.nonzero()]
    for i,[ind,peak,mag] in enumerate(zip(indx,peaks,mags)):
        rho = rollMap(rho,ind)
        rMM = mapHalf-steps
        rMP = mapHalf+steps+1
        rhoPeak = rho[int(rMM[0]):int(rMP[0]),int(rMM[1]):int(rMP[1]),int(rMM[2]):int(rMP[2])]
        peakInt = np.sum(rhoPeak)*res**3
        rX,rY,rZ = np.mgrid[int(rMM[0]):int(rMP[0]),int(rMM[1]):int(rMP[1]),int(rMM[2]):int(rMP[2])]
        x0 = [peakInt,mapHalf[0],mapHalf[1],mapHalf[2],2.0]          #magnitude, position & width(sig)
        result = HessianLSQ(peakFunc,x0,Hess=peakHess,
            args=(rX,rY,rZ,rhoPeak,res,SGData['SGLaue']),ftol=.01,maxcyc=10)
        x1 = result[0]
        if not np.any(x1 < 0):
            peak = (np.array(x1[1:4])-ind)/incre
        peak = fixSpecialPos(peak,SGData,Amat)
        rho = rollMap(rho,-ind)
    cent = np.ones(3)*.5      
    dzeros = np.sqrt(np.sum(np.inner(Amat,peaks)**2,axis=0))
    dcent = np.sqrt(np.sum(np.inner(Amat,peaks-cent)**2,axis=0))
    if Neg:     #want negative magnitudes for negative peaks
        return np.array(peaks),-np.array([mags,]).T,np.array([dzeros,]).T,np.array([dcent,]).T
    else:
        return np.array(peaks),np.array([mags,]).T,np.array([dzeros,]).T,np.array([dcent,]).T
    
def sortArray(data,pos,reverse=False):
    '''data is a list of items
    sort by pos in list; reverse if True
    '''
    T = []
    for i,M in enumerate(data):
        try:
            T.append((M[pos],i))
        except IndexError:
            return data
    D = dict(zip(T,data))
    T.sort()
    if reverse:
        T.reverse()
    X = []
    for key in T:
        X.append(D[key])
    return X

def PeaksEquiv(data,Ind):
    '''Find the equivalent map peaks for those selected. Works on the 
    contents of data['Map Peaks'].

    :param data: the phase data structure
    :param list Ind: list of selected peak indices
    :returns: augmented list of peaks including those related by symmetry to the
      ones in Ind

    '''        
    def Duplicate(xyz,peaks,Amat):
        if True in [np.allclose(np.inner(Amat,xyz),np.inner(Amat,peak),atol=0.5) for peak in peaks]:
            return True
        return False
                            
    generalData = data['General']
    Amat,Bmat = G2lat.cell2AB(generalData['Cell'][1:7])
    SGData = generalData['SGData']
    mapPeaks = data['Map Peaks']
    XYZ = np.array([xyz[1:4] for xyz in mapPeaks])
    Indx = {}
    for ind in Ind:
        xyz = np.array(mapPeaks[ind][1:4])
        xyzs = np.array([equiv[0] for equiv in G2spc.GenAtom(xyz,SGData,Move=True)])
        for jnd,xyz in enumerate(XYZ):       
            Indx[jnd] = Duplicate(xyz,xyzs,Amat)
    Ind = []
    for ind in Indx:
        if Indx[ind]:
            Ind.append(ind)
    return Ind
                
def PeaksUnique(data,Ind):
    '''Finds the symmetry unique set of peaks from those selected. Works on the 
    contents of data['Map Peaks']. 

    :param data: the phase data structure
    :param list Ind: list of selected peak indices
    :returns: the list of symmetry unique peaks from among those given in Ind

    '''        
#    XYZE = np.array([[equiv[0] for equiv in G2spc.GenAtom(xyz[1:4],SGData,Move=True)] for xyz in mapPeaks]) #keep this!!

    def noDuplicate(xyz,peaks,Amat):
        if True in [np.allclose(np.inner(Amat,xyz),np.inner(Amat,peak),atol=0.5) for peak in peaks]:
            return False
        return True
                            
    generalData = data['General']
    Amat,Bmat = G2lat.cell2AB(generalData['Cell'][1:7])
    SGData = generalData['SGData']
    mapPeaks = data['Map Peaks']
    Indx = {}
    XYZ = {}
    for ind in Ind:
        XYZ[ind] = np.array(mapPeaks[ind][1:4])
        Indx[ind] = True
    for ind in Ind:
        if Indx[ind]:
            xyz = XYZ[ind]
            for jnd in Ind:
                if ind != jnd and Indx[jnd]:                        
                    Equiv = G2spc.GenAtom(XYZ[jnd],SGData,Move=True)
                    xyzs = np.array([equiv[0] for equiv in Equiv])
                    Indx[jnd] = noDuplicate(xyz,xyzs,Amat)
    Ind = []
    for ind in Indx:
        if Indx[ind]:
            Ind.append(ind)
    return Ind

################################################################################
##### Dysnomia setup & return stuff
################################################################################
    

    
################################################################################
##### single peak fitting profile fxn stuff
################################################################################

def getCWsig(ins,pos):
    '''get CW peak profile sigma^2
    
    :param dict ins: instrument parameters with at least 'U', 'V', & 'W' 
      as values only
    :param float pos: 2-theta of peak
    :returns: float getCWsig: peak sigma^2
    
    '''
    tp = tand(pos/2.0)
    return ins['U']*tp**2+ins['V']*tp+ins['W']
    
def getCWsigDeriv(pos):
    '''get derivatives of CW peak profile sigma^2 wrt U,V, & W
    
    :param float pos: 2-theta of peak
    
    :returns: list getCWsigDeriv: d(sig^2)/dU, d(sig)/dV & d(sig)/dW
    
    '''
    tp = tand(pos/2.0)
    return tp**2,tp,1.0
    
def getCWgam(ins,pos):
    '''get CW peak profile gamma
    
    :param dict ins: instrument parameters with at least 'X', 'Y' & 'Z'
      as values only
    :param float pos: 2-theta of peak
    :returns: float getCWgam: peak gamma
    
    '''
    return ins['X']/cosd(pos/2.0)+ins['Y']*tand(pos/2.0)+ins.get('Z',0.0)
    
def getCWgamDeriv(pos):
    '''get derivatives of CW peak profile gamma wrt X, Y & Z
    
    :param float pos: 2-theta of peak
    
    :returns: list getCWgamDeriv: d(gam)/dX & d(gam)/dY
    
    '''
    return 1./cosd(pos/2.0),tand(pos/2.0),1.0
    
def getTOFsig(ins,dsp):
    '''get TOF peak profile sigma^2
    
    :param dict ins: instrument parameters with at least 'sig-0', 'sig-1' & 'sig-q'
      as values only
    :param float dsp: d-spacing of peak
    
    :returns: float getTOFsig: peak sigma^2
    
    '''
    return ins['sig-0']+ins['sig-1']*dsp**2+ins['sig-2']*dsp**4+ins['sig-q']*dsp
    
def getTOFsigDeriv(dsp):
    '''get derivatives of TOF peak profile sigma^2 wrt sig-0, sig-1, & sig-q
    
    :param float dsp: d-spacing of peak
    
    :returns: list getTOFsigDeriv: d(sig0/d(sig-0), d(sig)/d(sig-1) & d(sig)/d(sig-q)
    
    '''
    return 1.0,dsp**2,dsp**4,dsp
    
def getTOFgamma(ins,dsp):
    '''get TOF peak profile gamma
    
    :param dict ins: instrument parameters with at least 'X', 'Y' & 'Z'
      as values only
    :param float dsp: d-spacing of peak
    
    :returns: float getTOFgamma: peak gamma
    
    '''
    return ins['Z']+ins['X']*dsp+ins['Y']*dsp**2
    
def getTOFgammaDeriv(dsp):
    '''get derivatives of TOF peak profile gamma wrt X, Y & Z
    
    :param float dsp: d-spacing of peak
    
    :returns: list getTOFgammaDeriv: d(gam)/dX & d(gam)/dY
    
    '''
    return dsp,dsp**2,1.0
    
def getTOFbeta(ins,dsp):
    '''get TOF peak profile beta
    
    :param dict ins: instrument parameters with at least 'beat-0', 'beta-1' & 'beta-q'
      as values only
    :param float dsp: d-spacing of peak
    
    :returns: float getTOFbeta: peak beat
    
    '''
    return ins['beta-0']+ins['beta-1']/dsp**4+ins['beta-q']/dsp**2
    
def getTOFbetaDeriv(dsp):
    '''get derivatives of TOF peak profile beta wrt beta-0, beta-1, & beat-q
    
    :param float dsp: d-spacing of peak
    
    :returns: list getTOFbetaDeriv: d(beta)/d(beat-0), d(beta)/d(beta-1) & d(beta)/d(beta-q)
    
    '''
    return 1.0,1./dsp**4,1./dsp**2
    
def getTOFalpha(ins,dsp):
    '''get TOF peak profile alpha
    
    :param dict ins: instrument parameters with at least 'alpha'
      as values only
    :param float dsp: d-spacing of peak
    
    :returns: flaot getTOFalpha: peak alpha
    
    '''
    return ins['alpha']/dsp
    
def getTOFalphaDeriv(dsp):
    '''get derivatives of TOF peak profile beta wrt alpha
    
    :param float dsp: d-spacing of peak
    
    :returns: float getTOFalphaDeriv: d(alp)/d(alpha)
    
    '''
    return 1./dsp
    
def setPeakparms(Parms,Parms2,pos,mag,ifQ=False,useFit=False):
    '''set starting peak parameters for single peak fits from plot selection or auto selection
    
    :param dict Parms: instrument parameters dictionary
    :param dict Parms2: table lookup for TOF profile coefficients
    :param float pos: peak position in 2-theta, TOF or Q (ifQ=True)
    :param float mag: peak top magnitude from pick
    :param bool ifQ: True if pos in Q
    :param bool useFit: True if use fitted CW Parms values (not defaults)
    
    :returns: list XY: peak list entry:
        for CW: [pos,0,mag,1,sig,0,gam,0]
        for TOF: [pos,0,mag,1,alp,0,bet,0,sig,0,gam,0]
        NB: mag refinement set by default, all others off
    
    '''
    ind = 0
    if useFit:
        ind = 1
    ins = {}
    if 'C' in Parms['Type'][0]:                            #CW data - TOF later in an else
        for x in ['U','V','W','X','Y','Z']:
            ins[x] = Parms.get(x,[0.0,0.0])[ind]
        if ifQ:                              #qplot - convert back to 2-theta
            pos = 2.0*asind(pos*getWave(Parms)/(4*math.pi))
        sig = getCWsig(ins,pos)
        gam = getCWgam(ins,pos)           
        XY = [pos,0, mag,1, sig,0, gam,0]       #default refine intensity 1st
    else:
        if ifQ:
            dsp = 2.*np.pi/pos
            pos = Parms['difC']*dsp
        else:
            dsp = pos/Parms['difC'][1]
        if 'Pdabc' in Parms2:
            for x in ['sig-0','sig-1','sig-2','sig-q','X','Y','Z']:
                ins[x] = Parms.get(x,[0.0,0.0])[ind]
            Pdabc = Parms2['Pdabc'].T
            alp = np.interp(dsp,Pdabc[0],Pdabc[1])
            bet = np.interp(dsp,Pdabc[0],Pdabc[2])
        else:
            for x in ['alpha','beta-0','beta-1','beta-q','sig-0','sig-1','sig-2','sig-q','X','Y','Z']:
                ins[x] = Parms.get(x,[0.0,0.0])[ind]
            alp = getTOFalpha(ins,dsp)
            bet = getTOFbeta(ins,dsp)
        sig = getTOFsig(ins,dsp)
        gam = getTOFgamma(ins,dsp)
        XY = [pos,0,mag,1,alp,0,bet,0,sig,0,gam,0]
    return XY
    
################################################################################
##### MC/SA stuff
################################################################################

#scipy/optimize/anneal.py code modified by R. Von Dreele 2013
# Original Author: Travis Oliphant 2002
# Bug-fixes in 2006 by Tim Leslie


import numpy
from numpy import asarray, exp, squeeze, sign, \
     all, shape, array, where
from numpy import random

#__all__ = ['anneal']

class base_schedule(object):
    def __init__(self):
        self.dwell = 20
        self.lower = 0.
        self.upper = 1.
        self.Ninit = 50
        self.accepted = 0
        self.tests = 0
        self.feval = 0
        self.k = 0
        self.T = None

    def init(self, **options):
        self.__dict__.update(options)
        self.lower = asarray(self.lower)
        self.lower = where(self.lower == numpy.NINF, -_double_max, self.lower)
        self.upper = asarray(self.upper)
        self.upper = where(self.upper == numpy.PINF, _double_max, self.upper)
        self.k = 0
        self.accepted = 0
        self.feval = 0
        self.tests = 0

    def getstart_temp(self, best_state):
        """ Find a matching starting temperature and starting parameters vector
        i.e. find x0 such that func(x0) = T0.

        :param best_state: _state
            A _state object to store the function value and x0 found.

        :returns: x0 : array
            The starting parameters vector.
        """

        assert(not self.dims is None)
        lrange = self.lower
        urange = self.upper
        fmax = _double_min
        fmin = _double_max
        for _ in range(self.Ninit):
            x0 = random.uniform(size=self.dims)*(urange-lrange) + lrange
            fval = self.func(x0, *self.args)
            self.feval += 1
            if fval > fmax:
                fmax = fval
            if fval < fmin:
                fmin = fval
                best_state.cost = fval
                best_state.x = array(x0)

        self.T0 = (fmax-fmin)*1.5
        return best_state.x
        
    def set_range(self,x0,frac):
        delrange = frac*(self.upper-self.lower)
        self.upper = x0+delrange
        self.lower = x0-delrange

    def accept_test(self, dE):
        T = self.T
        self.tests += 1
        if dE < 0:
            self.accepted += 1
            return 1
        p = exp(-dE*1.0/T)
        if (p > random.uniform(0.0, 1.0)):
            self.accepted += 1
            return 1
        return 0

    def update_guess(self, x0):
        return np.squeeze(np.random.uniform(0.,1.,size=self.dims))*(self.upper-self.lower)+self.lower

    def update_temp(self, x0):
        pass

class fast_sa(base_schedule):
    def init(self, **options):
        self.__dict__.update(options)

    def update_guess(self, x0):
        x0 = asarray(x0)
        u = squeeze(random.uniform(0.0, 1.0, size=self.dims))
        T = self.T
        xc = (sign(u-0.5)*T*((1+1.0/T)**abs(2*u-1)-1.0)+1.0)/2.0
        xnew = xc*(self.upper - self.lower)+self.lower
        return xnew

    def update_temp(self):
        self.T = self.T0*exp(-self.c * self.k**(self.quench))
        self.k += 1
        return

class log_sa(base_schedule):        #OK

    def init(self,**options):
        self.__dict__.update(options)
        
    def update_guess(self,x0):     #same as default #TODO - is this a reasonable update procedure?
        u = squeeze(random.uniform(0.0, 1.0, size=self.dims))
        T = self.T
        xc = (sign(u-0.5)*T*((1+1.0/T)**abs(2*u-1)-1.0)+1.0)/2.0
        xnew = xc*(self.upper - self.lower)+self.lower
        return xnew
        
    def update_temp(self):
        self.k += 1
        self.T = self.T0*self.slope**self.k
        
class _state(object):
    def __init__(self):
        self.x = None
        self.cost = None

def makeTsched(data):
    if data['Algorithm'] == 'fast':
        sched = fast_sa()
        sched.quench = data['fast parms'][0]
        sched.c = data['fast parms'][1]
    elif data['Algorithm'] == 'log':
        sched = log_sa()
        sched.slope = data['log slope']
    sched.T0 = data['Annealing'][0]
    if not sched.T0:
        sched.T0 = 50.
    Tf = data['Annealing'][1]
    if not Tf:
        Tf = 0.001
    Tsched = [sched.T0,]
    while Tsched[-1] > Tf:
        sched.update_temp()
        Tsched.append(sched.T)
    return Tsched[1:]
    
def anneal(func, x0, args=(), schedule='fast', 
           T0=None, Tf=1e-12, maxeval=None, maxaccept=None, maxiter=400,
           feps=1e-6, quench=1.0, c=1.0,
           lower=-100, upper=100, dwell=50, slope=0.9,ranStart=False,
           ranRange=0.10,autoRan=False,dlg=None):
    """Minimize a function using simulated annealing.

    Schedule is a schedule class implementing the annealing schedule.
    Available ones are 'fast', 'cauchy', 'boltzmann'

    :param callable func: f(x, \*args)
        Function to be optimized.
    :param ndarray x0:
        Initial guess.
    :param tuple args: 
        Extra parameters to `func`.
    :param base_schedule schedule: 
        Annealing schedule to use (a class).
    :param float T0: 
        Initial Temperature (estimated as 1.2 times the largest
        cost-function deviation over random points in the range).
    :param float Tf: 
        Final goal temperature.
    :param int maxeval: 
        Maximum function evaluations.
    :param int maxaccept:
        Maximum changes to accept.
    :param int maxiter: 
        Maximum cooling iterations.
    :param float feps:
        Stopping relative error tolerance for the function value in
        last four coolings.
    :param float quench,c:
        Parameters to alter fast_sa schedule.
    :param float/ndarray lower,upper: 
        Lower and upper bounds on `x`.
    :param int dwell:
        The number of times to search the space at each temperature.
    :param float slope: 
        Parameter for log schedule
    :param bool ranStart=False:
        True for set 10% of ranges about x 

    :returns: (xmin, Jmin, T, feval, iters, accept, retval) where

     * xmin (ndarray): Point giving smallest value found.
     * Jmin (float): Minimum value of function found.
     * T (float): Final temperature.
     * feval (int): Number of function evaluations.
     * iters (int): Number of cooling iterations.
     * accept (int): Number of tests accepted.
     * retval (int): Flag indicating stopping condition:

              *  0: Points no longer changing
              *  1: Cooled to final temperature
              *  2: Maximum function evaluations
              *  3: Maximum cooling iterations reached
              *  4: Maximum accepted query locations reached
              *  5: Final point not the minimum amongst encountered points

    *Notes*:
    Simulated annealing is a random algorithm which uses no derivative
    information from the function being optimized. In practice it has
    been more useful in discrete optimization than continuous
    optimization, as there are usually better algorithms for continuous
    optimization problems.

    Some experimentation by trying the difference temperature
    schedules and altering their parameters is likely required to
    obtain good performance.

    The randomness in the algorithm comes from random sampling in numpy.
    To obtain the same results you can call numpy.random.seed with the
    same seed immediately before calling scipy.optimize.anneal.

    We give a brief description of how the three temperature schedules
    generate new points and vary their temperature. Temperatures are
    only updated with iterations in the outer loop. The inner loop is
    over range(dwell), and new points are generated for
    every iteration in the inner loop. (Though whether the proposed
    new points are accepted is probabilistic.)

    For readability, let d denote the dimension of the inputs to func.
    Also, let x_old denote the previous state, and k denote the
    iteration number of the outer loop. All other variables not
    defined below are input variables to scipy.optimize.anneal itself.

    In the 'fast' schedule the updates are ::

        u ~ Uniform(0, 1, size=d)
        y = sgn(u - 0.5) * T * ((1+ 1/T)**abs(2u-1) -1.0)
        xc = y * (upper - lower)
        x_new = x_old + xc

        T_new = T0 * exp(-c * k**quench)

    """
    
    ''' Scipy license:
        Copyright (c) 2001, 2002 Enthought, Inc.
    All rights reserved.
    
    Copyright (c) 2003-2016 SciPy Developers.
    All rights reserved.
    
    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:
    
      a. Redistributions of source code must retain the above copyright notice,
         this list of conditions and the following disclaimer.
      b. Redistributions in binary form must reproduce the above copyright
         notice, this list of conditions and the following disclaimer in the
         documentation and/or other materials provided with the distribution.
      c. Neither the name of Enthought nor the names of the SciPy Developers
         may be used to endorse or promote products derived from this software
         without specific prior written permission.
    '''
    x0 = asarray(x0)
    lower = asarray(lower)
    upper = asarray(upper)

    schedule = eval(schedule+'_sa()')
    #   initialize the schedule
    schedule.init(dims=shape(x0),func=func,args=args,T0=T0,lower=lower, upper=upper,
        c=c, quench=quench, dwell=dwell, slope=slope)

    current_state, last_state, best_state = _state(), _state(), _state()
    if ranStart:
        schedule.set_range(x0,ranRange)
    if T0 is None:
        x0 = schedule.getstart_temp(best_state)
    else:
        x0 = random.uniform(size=len(x0))*(upper-lower) + lower
        best_state.x = None
        best_state.cost = numpy.Inf

    last_state.x = asarray(x0).copy()
    fval = func(x0,*args)
    schedule.feval += 1
    last_state.cost = fval
    if last_state.cost < best_state.cost:
        best_state.cost = fval
        best_state.x = asarray(x0).copy()
    schedule.T = schedule.T0
    fqueue = [100, 300, 500, 700]
    iters = 1
    keepGoing = True
    bestn = 0
    while keepGoing:
        retval = 0
        for n in range(dwell):
            current_state.x = schedule.update_guess(last_state.x)
            current_state.cost = func(current_state.x,*args)
            schedule.feval += 1

            dE = current_state.cost - last_state.cost
            if schedule.accept_test(dE):
                last_state.x = current_state.x.copy()
                last_state.cost = current_state.cost
                if last_state.cost < best_state.cost:
                    best_state.x = last_state.x.copy()
                    best_state.cost = last_state.cost
                    bestn = n
                    if best_state.cost < 1.0 and autoRan:
                        schedule.set_range(x0,best_state.cost/2.)                        
        if dlg:
            GoOn = dlg.Update(min(100.,best_state.cost*100),
                newmsg='%s%8.5f, %s%d\n%s%8.4f%s'%('Temperature =',schedule.T, \
                    'Best trial:',bestn,  \
                    'MC/SA Residual:',best_state.cost*100,'%', \
                    ))[0]
            if not GoOn:
                best_state.x = last_state.x.copy()
                best_state.cost = last_state.cost
                retval = 5
        schedule.update_temp()
        iters += 1
        # Stopping conditions
        # 0) last saved values of f from each cooling step
        #     are all very similar (effectively cooled)
        # 1) Tf is set and we are below it
        # 2) maxeval is set and we are past it
        # 3) maxiter is set and we are past it
        # 4) maxaccept is set and we are past it
        # 5) user canceled run via progress bar

        fqueue.append(squeeze(last_state.cost))
        fqueue.pop(0)
        af = asarray(fqueue)*1.0
        if retval == 5:
            G2fil.G2Print ('Error: User terminated run; incomplete MC/SA')
            keepGoing = False
            break
        if all(abs((af-af[0])/af[0]) < feps):
            retval = 0
            if abs(af[-1]-best_state.cost) > feps*10:
                retval = 5
                G2fil.G2Print (" Warning: Cooled to %.4f > selected Tmin %.4f in %d steps"%(squeeze(last_state.cost),Tf,iters-1))
            break
        if (Tf is not None) and (schedule.T < Tf):
#            print ' Minimum T reached in %d steps'%(iters-1)
            retval = 1
            break
        if (maxeval is not None) and (schedule.feval > maxeval):
            retval = 2
            break
        if (iters > maxiter):
            G2fil.G2Print  (" Warning: Maximum number of iterations exceeded.")
            retval = 3
            break
        if (maxaccept is not None) and (schedule.accepted > maxaccept):
            retval = 4
            break

    return best_state.x, best_state.cost, schedule.T, \
           schedule.feval, iters, schedule.accepted, retval

def worker(iCyc,data,RBdata,reflType,reflData,covData,out_q,out_t,out_n,nprocess=-1):
    outlist = []
    timelist = []
    nsflist = []
    random.seed(int(time.time())%100000+nprocess)   #make sure each process has a different random start
    for n in range(iCyc):
        result = mcsaSearch(data,RBdata,reflType,reflData,covData,None,False)         #mcsa result,time,rcov
        outlist.append(result[0])
        timelist.append(result[1])
        nsflist.append(result[2])
        G2fil.G2Print (' MC/SA final fit: %.3f%% structure factor time: %.3f'%(100*result[0][2],result[1]))
    out_q.put(outlist)
    out_t.put(timelist)
    out_n.put(nsflist)

def MPmcsaSearch(nCyc,data,RBdata,reflType,reflData,covData,nprocs):
    import multiprocessing as mp
    
    out_q = mp.Queue()
    out_t = mp.Queue()
    out_n = mp.Queue()
    procs = []
    totsftime = 0.
    totnsf = 0
    iCyc = np.zeros(nprocs)
    for i in range(nCyc):
        iCyc[i%nprocs] += 1
    for i in range(nprocs):
        p = mp.Process(target=worker,args=(int(iCyc[i]),data,RBdata,reflType,reflData,covData,out_q,out_t,out_n,i))
        procs.append(p)
        p.start()
    resultlist = []
    for i in range(nprocs):
        resultlist += out_q.get()
        totsftime += np.sum(out_t.get())
        totnsf += np.sum(out_n.get())
    for p in procs:
        p.join()
    return resultlist,totsftime,totnsf

def mcsaSearch(data,RBdata,reflType,reflData,covData,pgbar,start=True):
    '''default doc string
    
    :param type name: description
    
    :returns: type name: description
    '''
   
    class RandomDisplacementBounds(object):
        """random displacement with bounds"""
        def __init__(self, xmin, xmax, stepsize=0.5):
            self.xmin = xmin
            self.xmax = xmax
            self.stepsize = stepsize
    
        def __call__(self, x):
            """take a random step but ensure the new position is within the bounds"""
            while True:
                # this could be done in a much more clever way, but it will work for example purposes
                steps = self.xmax-self.xmin
                xnew = x + np.random.uniform(-self.stepsize*steps, self.stepsize*steps, np.shape(x))
                if np.all(xnew < self.xmax) and np.all(xnew > self.xmin):
                    break
            return xnew
    
    global tsum,nsum
    tsum = 0.
    nsum = 0
    
    def getMDparms(item,pfx,parmDict,varyList):
        parmDict[pfx+'MDaxis'] = item['axis']
        parmDict[pfx+'MDval'] = item['Coef'][0]
        if item['Coef'][1]:
            varyList += [pfx+'MDval',]
            limits = item['Coef'][2]
            lower.append(limits[0])
            upper.append(limits[1])
                        
    def getAtomparms(item,pfx,aTypes,SGData,parmDict,varyList):
        parmDict[pfx+'Atype'] = item['atType']
        aTypes |= set([item['atType'],]) 
        pstr = ['Ax','Ay','Az']
        XYZ = [0,0,0]
        for i in range(3):
            name = pfx+pstr[i]
            parmDict[name] = item['Pos'][0][i]
            XYZ[i] = parmDict[name]
            if item['Pos'][1][i]:
                varyList += [name,]
                limits = item['Pos'][2][i]
                lower.append(limits[0])
                upper.append(limits[1])
        parmDict[pfx+'Amul'] = len(list(G2spc.GenAtom(XYZ,SGData)))
            
    def getRBparms(item,mfx,aTypes,RBdata,SGData,atNo,parmDict,varyList):
        parmDict[mfx+'MolCent'] = item['MolCent']
        parmDict[mfx+'RBId'] = item['RBId']
        pstr = ['Px','Py','Pz']
        ostr = ['Qa','Qi','Qj','Qk']    #angle,vector not quaternion
        for i in range(3):
            name = mfx+pstr[i]
            parmDict[name] = item['Pos'][0][i]
            if item['Pos'][1][i]:
                varyList += [name,]
                limits = item['Pos'][2][i]
                lower.append(limits[0])
                upper.append(limits[1])
        AV = item['Ori'][0]
        A = AV[0]
        V = AV[1:]
        for i in range(4):
            name = mfx+ostr[i]
            if i:
                parmDict[name] = V[i-1]
            else:
                parmDict[name] = A
            if item['Ovar'] == 'AV':
                varyList += [name,]
                limits = item['Ori'][2][i]
                lower.append(limits[0])
                upper.append(limits[1])
            elif item['Ovar'] == 'A' and not i:
                varyList += [name,]
                limits = item['Ori'][2][i]
                lower.append(limits[0])
                upper.append(limits[1])
        if 'Tor' in item:      #'Tor' not there for 'Vector' RBs
            for i in range(len(item['Tor'][0])):
                name = mfx+'Tor'+str(i)
                parmDict[name] = item['Tor'][0][i]
                if item['Tor'][1][i]:
                    varyList += [name,]
                    limits = item['Tor'][2][i]
                    lower.append(limits[0])
                    upper.append(limits[1])
        atypes = RBdata[item['Type']][item['RBId']]['rbTypes']
        aTypes |= set(atypes)
        atNo += len(atypes)
        return atNo
                
    def GetAtomM(Xdata,SGData):
        Mdata = []
        for xyz in Xdata:
            Mdata.append(float(len(list(G2spc.GenAtom(xyz,SGData)))))
        return np.array(Mdata)
        
    def GetAtomT(RBdata,parmDict):
        'Needs a doc string'
        atNo = parmDict['atNo']
        nfixAt = parmDict['nfixAt']
        Tdata = atNo*[' ',]
        for iatm in range(nfixAt):
            parm = ':'+str(iatm)+':Atype'
            if parm in parmDict:
                Tdata[iatm] = aTypes.index(parmDict[parm])
        iatm = nfixAt
        for iObj in range(parmDict['nObj']):
            pfx = str(iObj)+':'
            if parmDict[pfx+'Type'] in ['Vector','Residue']:
                if parmDict[pfx+'Type'] == 'Vector':
                    RBRes = RBdata['Vector'][parmDict[pfx+'RBId']]
                    nAtm = len(RBRes['rbVect'][0])
                else:       #Residue
                    RBRes = RBdata['Residue'][parmDict[pfx+'RBId']]
                    nAtm = len(RBRes['rbXYZ'])
                for i in range(nAtm):
                    Tdata[iatm] = aTypes.index(RBRes['rbTypes'][i])
                    iatm += 1
            elif parmDict[pfx+'Type'] == 'Atom':
                atNo = parmDict[pfx+'atNo']
                parm = pfx+'Atype'              #remove extra ':'
                if parm in parmDict:
                    Tdata[atNo] = aTypes.index(parmDict[parm])
                iatm += 1
            else:
                continue        #skips March Dollase
        return Tdata
        
    def GetAtomX(RBdata,parmDict):
        'Needs a doc string'
        Bmat = parmDict['Bmat']
        atNo = parmDict['atNo']
        nfixAt = parmDict['nfixAt']
        Xdata = np.zeros((3,atNo))
        keys = {':Ax':Xdata[0],':Ay':Xdata[1],':Az':Xdata[2]}
        for iatm in range(nfixAt):
            for key in keys:
                parm = ':'+str(iatm)+key
                if parm in parmDict:
                    keys[key][iatm] = parmDict[parm]
        iatm = nfixAt
        for iObj in range(parmDict['nObj']):
            pfx = str(iObj)+':'
            if parmDict[pfx+'Type'] in ['Vector','Residue']:
                if parmDict[pfx+'Type'] == 'Vector':
                    RBRes = RBdata['Vector'][parmDict[pfx+'RBId']]
                    vecs = RBRes['rbVect']
                    mags = RBRes['VectMag']
                    Cart = np.zeros_like(vecs[0])
                    for vec,mag in zip(vecs,mags):
                        Cart += vec*mag
                elif parmDict[pfx+'Type'] == 'Residue':
                    RBRes = RBdata['Residue'][parmDict[pfx+'RBId']]
                    Cart = np.array(RBRes['rbXYZ'])
                    for itor,seq in enumerate(RBRes['rbSeq']):
                        QuatA = AVdeg2Q(parmDict[pfx+'Tor'+str(itor)],Cart[seq[0]]-Cart[seq[1]])
                        Cart[seq[3]] = prodQVQ(QuatA,Cart[seq[3]]-Cart[seq[1]])+Cart[seq[1]]
                if parmDict[pfx+'MolCent'][1]:
                    Cart -= parmDict[pfx+'MolCent'][0]
                Qori = AVdeg2Q(parmDict[pfx+'Qa'],[parmDict[pfx+'Qi'],parmDict[pfx+'Qj'],parmDict[pfx+'Qk']])
                Pos = np.array([parmDict[pfx+'Px'],parmDict[pfx+'Py'],parmDict[pfx+'Pz']])
                Xdata.T[iatm:iatm+len(Cart)] = np.inner(Bmat,prodQVQ(Qori,Cart)).T+Pos
                iatm += len(Cart)
            elif parmDict[pfx+'Type'] == 'Atom':
                atNo = parmDict[pfx+'atNo']
                for key in keys:
                    parm = pfx+key[1:]              #remove extra ':'
                    if parm in parmDict:
                        keys[key][atNo] = parmDict[parm]
                iatm += 1
            else:
                continue        #skips March Dollase
        return Xdata.T
        
    def getAllTX(Tdata,Mdata,Xdata,SGM,SGT):
        allX = np.inner(Xdata,SGM)+SGT
        allT = np.repeat(Tdata,allX.shape[1])
        allM = np.repeat(Mdata,allX.shape[1])
        allX = np.reshape(allX,(-1,3))
        return allT,allM,allX

    def getAllX(Xdata,SGM,SGT):
        allX = np.inner(Xdata,SGM)+SGT
        allX = np.reshape(allX,(-1,3))
        return allX
        
    def normQuaternions(RBdata,parmDict,varyList,values):
        for iObj in range(parmDict['nObj']):
            pfx = str(iObj)+':'
            if parmDict[pfx+'Type'] in ['Vector','Residue']:
                Qori = AVdeg2Q(parmDict[pfx+'Qa'],[parmDict[pfx+'Qi'],parmDict[pfx+'Qj'],parmDict[pfx+'Qk']])
                A,V = Q2AVdeg(Qori)
                for i,name in enumerate(['Qa','Qi','Qj','Qk']):
                    if i:
                        parmDict[pfx+name] = V[i-1]
                    else:
                        parmDict[pfx+name] = A
        
    def mcsaCalc(values,refList,rcov,cosTable,ifInv,allFF,RBdata,varyList,parmDict):
        ''' Compute structure factors for all h,k,l for phase
        input:
            refList: [ref] where each ref = h,k,l,m,d,...
            rcov:   array[nref,nref] covariance terms between Fo^2 values
            ifInv:  bool True if centrosymmetric
            allFF: array[nref,natoms] each value is mult*FF(H)/max(mult)
            RBdata: [dict] rigid body dictionary
            varyList: [list] names of varied parameters in MC/SA (not used here)           
            ParmDict: [dict] problem parameters
        puts result F^2 in each ref[5] in refList
        returns:
            delt-F*rcov*delt-F/sum(Fo^2)
        '''   
            
        global tsum,nsum
        t0 = time.time()
        parmDict.update(dict(zip(varyList,values)))             #update parameter tables
        Xdata = GetAtomX(RBdata,parmDict)                       #get new atom coords from RB
        allX = getAllX(Xdata,SGM,SGT)                           #fill unit cell - dups. OK
        MDval = parmDict['0:MDval']                             #get March-Dollase coeff
        HX2pi = 2.*np.pi*np.inner(allX,refList[:3].T)           #form 2piHX for every H,X pair
        Aterm = refList[3]*np.sum(allFF*np.cos(HX2pi),axis=0)**2    #compute real part for all H
        refList[5] = Aterm
        if not ifInv:
            refList[5] += refList[3]*np.sum(allFF*np.sin(HX2pi),axis=0)**2    #imaginary part for all H
        if len(cosTable):        #apply MD correction
            refList[5] *= np.sum(np.sqrt((MDval/(cosTable*(MDval**3-1.)+1.))**3),axis=1)/cosTable.shape[1]
        sumFcsq = np.sum(refList[5])
        scale = parmDict['sumFosq']/sumFcsq
        refList[5] *= scale
        refList[6] = refList[4]-refList[5]
        M = np.inner(refList[6],np.inner(rcov,refList[6]))
        tsum += (time.time()-t0)
        nsum += 1
        return np.sqrt(M/np.sum(refList[4]**2))
    
    def MCSAcallback(x, f,accept):
        return not pgbar.Update(min(100.,f*100),
            newmsg='%s%8.4f%s'%('MC/SA Residual:',f*100,'%'))[0]

    sq2pi = np.sqrt(2*np.pi)
    sq4pi = np.sqrt(4*np.pi)
    generalData = data['General']
    Amat,Bmat = G2lat.cell2AB(generalData['Cell'][1:7])
    Gmat,gmat = G2lat.cell2Gmat(generalData['Cell'][1:7])
    SGData = generalData['SGData']
    SGM = np.array([SGData['SGOps'][i][0] for i in range(len(SGData['SGOps']))])
    SGMT = np.array([SGData['SGOps'][i][0].T for i in range(len(SGData['SGOps']))])
    SGT = np.array([SGData['SGOps'][i][1] for i in range(len(SGData['SGOps']))])
    fixAtoms = data['Atoms']                       #if any
    cx,ct,cs = generalData['AtomPtrs'][:3]
    aTypes = set([])
    parmDict = {'Bmat':Bmat,'Gmat':Gmat}
    varyList = []
    atNo = 0
    for atm in fixAtoms:
        pfx = ':'+str(atNo)+':'
        parmDict[pfx+'Atype'] = atm[ct]
        aTypes |= set([atm[ct],])
        pstr = ['Ax','Ay','Az']
        parmDict[pfx+'Amul'] = atm[cs+1]
        for i in range(3):
            name = pfx+pstr[i]
            parmDict[name] = atm[cx+i]
        atNo += 1
    parmDict['nfixAt'] = len(fixAtoms)        
    MCSA = generalData['MCSA controls']
    reflName = MCSA['Data source']
    MCSAObjs = data['MCSA']['Models']               #list of MCSA models
    upper = []
    lower = []
    MDvec = np.zeros(3)
    for i,item in enumerate(MCSAObjs):
        mfx = str(i)+':'
        parmDict[mfx+'Type'] = item['Type']
        if item['Type'] == 'MD':
            getMDparms(item,mfx,parmDict,varyList)
            MDvec = np.array(item['axis'])
        elif item['Type'] == 'Atom':
            getAtomparms(item,mfx,aTypes,SGData,parmDict,varyList)
            parmDict[mfx+'atNo'] = atNo
            atNo += 1
        elif item['Type'] in ['Residue','Vector']:
            atNo = getRBparms(item,mfx,aTypes,RBdata,SGData,atNo,parmDict,varyList)
    parmDict['atNo'] = atNo                 #total no. of atoms
    parmDict['nObj'] = len(MCSAObjs)
    aTypes = list(aTypes)
    Tdata = GetAtomT(RBdata,parmDict)
    Xdata = GetAtomX(RBdata,parmDict)
    Mdata = GetAtomM(Xdata,SGData)
    allT,allM = getAllTX(Tdata,Mdata,Xdata,SGM,SGT)[:2]
    FFtables = G2el.GetFFtable(aTypes)
    refs = []
    allFF = []
    cosTable = []
    sumFosq = 0
    if 'PWDR' in reflName:
        for ref in reflData:
            h,k,l,m,d,pos,sig,gam,f = ref[:9]
            if d >= MCSA['dmin']:
                sig = np.sqrt(sig)      #var -> sig in centideg
                sig = .01*G2pwd.getgamFW(gam,sig)        #sig,gam -> FWHM in deg
                SQ = 0.25/d**2
                allFF.append(allM*[G2el.getFFvalues(FFtables,SQ,True)[i] for i in allT]/np.max(allM))
                refs.append([h,k,l,m,f*m,pos,sig])
                sumFosq += f*m
                Heqv = np.inner(np.array([h,k,l]),SGMT)
                cosTable.append(G2lat.CosAngle(Heqv,MDvec,Gmat))
        nRef = len(refs)
        cosTable = np.array(cosTable)**2
        rcov = np.zeros((nRef,nRef))
        for iref,refI in enumerate(refs):
            rcov[iref][iref] = 1./(sq4pi*refI[6])
            for jref,refJ in enumerate(refs[:iref]):
                t1 = refI[6]**2+refJ[6]**2
                t2 = (refJ[5]-refI[5])**2/(2.*t1)
                if t2 > 10.:
                    rcov[iref][jref] = 0.
                else:
                    rcov[iref][jref] = 1./(sq2pi*np.sqrt(t1)*np.exp(t2))
        rcov += (rcov.T-np.diagflat(np.diagonal(rcov)))
        Rdiag = np.sqrt(np.diag(rcov))
        Rnorm = np.outer(Rdiag,Rdiag)
        rcov /= Rnorm
    elif 'Pawley' in reflName:  #need a bail out if Pawley cov matrix doesn't exist.
        vNames = []
        pfx = str(data['pId'])+'::PWLref:'
        for iref,refI in enumerate(reflData):           #Pawley reflection set
            h,k,l,m,d,v,f,s = refI
            if d >= MCSA['dmin'] and v:       #skip unrefined ones
                vNames.append(pfx+str(iref))
                SQ = 0.25/d**2
                allFF.append(allM*[G2el.getFFvalues(FFtables,SQ,True)[i] for i in allT]/np.max(allM))
                refs.append([h,k,l,m,f*m,iref,0.])
                sumFosq += f*m
                Heqv = np.inner(np.array([h,k,l]),SGMT)
                cosTable.append(G2lat.CosAngle(Heqv,MDvec,Gmat))
        cosTable = np.array(cosTable)**2
        nRef = len(refs)
#        if generalData['doPawley'] and (covData['freshCOV'] or  MCSA['newDmin']):
        if covData['freshCOV'] or  MCSA['newDmin']:
            vList = covData['varyList']
            covMatrix = covData['covMatrix']
            rcov = getVCov(vNames,vList,covMatrix)
            rcov += (rcov.T-np.diagflat(np.diagonal(rcov)))
            Rdiag = np.sqrt(np.diag(rcov))
            Rdiag = np.where(Rdiag,Rdiag,1.0)
            Rnorm = np.outer(Rdiag,Rdiag)
            rcov /= Rnorm
            MCSA['rcov'] = rcov
            covData['freshCOV'] = False
            MCSA['newDmin'] = False
        else:
            rcov = MCSA['rcov']
    elif 'HKLF' in reflName:
        for ref in reflData:
            [h,k,l,m,d],f = ref[:5],ref[6]
            if d >= MCSA['dmin']:
                SQ = 0.25/d**2
                allFF.append(allM*[G2el.getFFvalues(FFtables,SQ,True)[i] for i in allT]/np.max(allM))
                refs.append([h,k,l,m,f*m,0.,0.])
                sumFosq += f*m
        nRef = len(refs)
        rcov = np.identity(len(refs))
    allFF = np.array(allFF).T
    refs = np.array(refs).T
    if start:
        G2fil.G2Print (' Minimum d-spacing used: %.2f No. reflections used: %d'%(MCSA['dmin'],nRef))
        G2fil.G2Print (' Number of parameters varied: %d'%(len(varyList)))
        start = False
    parmDict['sumFosq'] = sumFosq
    x0 = [parmDict[val] for val in varyList]
    ifInv = SGData['SGInv']
    bounds = np.array(list(zip(lower,upper)))
    if MCSA['Algorithm'] == 'Basin Hopping':
#        import basinhopping as bs
        take_step = RandomDisplacementBounds(np.array(lower), np.array(upper))
        results = so.basinhopping(mcsaCalc,x0,take_step=take_step,disp=True,T=MCSA['Annealing'][0],
                interval=MCSA['Annealing'][2]/10,niter=MCSA['Annealing'][2],minimizer_kwargs={'method':'L-BFGS-B','bounds':bounds,
                'args':(refs,rcov,cosTable,ifInv,allFF,RBdata,varyList,parmDict)},callback=MCSAcallback)
    else:
        T0 = MCSA['Annealing'][0]
        if not T0:
            T0 = None
        results = anneal(mcsaCalc,x0,args=(refs,rcov,cosTable,ifInv,allFF,RBdata,varyList,parmDict),
            schedule=MCSA['Algorithm'], dwell=MCSA['Annealing'][2],maxiter=10000,
            T0=T0, Tf=MCSA['Annealing'][1],
            quench=MCSA['fast parms'][0], c=MCSA['fast parms'][1], 
            lower=lower, upper=upper, slope=MCSA['log slope'],ranStart=MCSA.get('ranStart',False),
            ranRange=MCSA.get('ranRange',10.)/100.,autoRan=MCSA.get('autoRan',False),dlg=pgbar)
        G2fil.G2Print (' Acceptance rate: %.2f%% MCSA residual: %.2f%%'%(100.*results[5]/results[3],100.*results[1]))
        results = so.minimize(mcsaCalc,results[0],method='L-BFGS-B',args=(refs,rcov,cosTable,ifInv,allFF,RBdata,varyList,parmDict),
            bounds=bounds,)
    mcsaCalc(results['x'],refs,rcov,cosTable,ifInv,allFF,RBdata,varyList,parmDict)
    Result = [False,False,results['fun'],0.0,]+list(results['x'])
    Result.append(varyList)
    return Result,tsum,nsum,rcov

        
################################################################################
##### Quaternion stuff
################################################################################

def prodQQ(QA,QB):
    ''' Grassman quaternion product
        QA,QB quaternions; q=r+ai+bj+ck
    '''
    D = np.zeros(4)
    D[0] = QA[0]*QB[0]-QA[1]*QB[1]-QA[2]*QB[2]-QA[3]*QB[3]
    D[1] = QA[0]*QB[1]+QA[1]*QB[0]+QA[2]*QB[3]-QA[3]*QB[2]
    D[2] = QA[0]*QB[2]-QA[1]*QB[3]+QA[2]*QB[0]+QA[3]*QB[1]
    D[3] = QA[0]*QB[3]+QA[1]*QB[2]-QA[2]*QB[1]+QA[3]*QB[0]
    
#    D[0] = QA[0]*QB[0]-np.dot(QA[1:],QB[1:])
#    D[1:] = QA[0]*QB[1:]+QB[0]*QA[1:]+np.cross(QA[1:],QB[1:])
    
    return D
    
def normQ(QA):
    ''' get length of quaternion & normalize it
        q=r+ai+bj+ck
    '''
    n = np.sqrt(np.sum(np.array(QA)**2))
    return QA/n
    
def invQ(Q):
    '''
        get inverse of quaternion
        q=r+ai+bj+ck; q* = r-ai-bj-ck
    '''
    return Q*np.array([1,-1,-1,-1])
    
def prodQVQ(Q,V):
    """
    compute the quaternion vector rotation qvq-1 = v'
    q=r+ai+bj+ck
    """
    T2 = Q[0]*Q[1]
    T3 = Q[0]*Q[2]
    T4 = Q[0]*Q[3]
    T5 = -Q[1]*Q[1]
    T6 = Q[1]*Q[2]
    T7 = Q[1]*Q[3]
    T8 = -Q[2]*Q[2]
    T9 = Q[2]*Q[3]
    T10 = -Q[3]*Q[3]
    M = np.array([[T8+T10,T6-T4,T3+T7],[T4+T6,T5+T10,T9-T2],[T7-T3,T2+T9,T5+T8]])
    VP = 2.*np.inner(V,M)
    return VP+V 
    
def Q2Mat(Q):
    ''' make rotation matrix from quaternion
        q=r+ai+bj+ck
    '''
    QN = normQ(Q)
    aa = QN[0]**2
    ab = QN[0]*QN[1]
    ac = QN[0]*QN[2]
    ad = QN[0]*QN[3]
    bb = QN[1]**2
    bc = QN[1]*QN[2]
    bd = QN[1]*QN[3]
    cc = QN[2]**2
    cd = QN[2]*QN[3]
    dd = QN[3]**2
    M = [[aa+bb-cc-dd, 2.*(bc-ad),  2.*(ac+bd)],
        [2*(ad+bc),   aa-bb+cc-dd,  2.*(cd-ab)],
        [2*(bd-ac),    2.*(ab+cd), aa-bb-cc+dd]]
    return np.array(M)
    
def AV2Q(A,V):
    ''' convert angle (radians) & vector to quaternion
        q=r+ai+bj+ck
    '''
    Q = np.zeros(4)
    d = nl.norm(np.array(V))
    if d:
        V = V/d
        if not A:       #==0.
            A = 2.*np.pi
        p = A/2.
        Q[0] = np.cos(p)
        Q[1:4] = V*np.sin(p)
    else:
        Q[3] = 1.
    return Q
    
def AVdeg2Q(A,V):
    ''' convert angle (degrees) & vector to quaternion
        q=r+ai+bj+ck
    '''
    Q = np.zeros(4)
    d = nl.norm(np.array(V))
    if not A:       #== 0.!
        A = 360.
    if d:
        V = V/d
        p = A/2.
        Q[0] = cosd(p)
        Q[1:4] = V*sind(p)
    else:
        Q[3] = 1.
    return Q
    
def Q2AVdeg(Q):
    ''' convert quaternion to angle (degrees 0-360) & normalized vector
        q=r+ai+bj+ck
    '''
    A = 2.*acosd(Q[0])
    V = np.array(Q[1:])
    V = V/sind(A/2.)
    return A,V
    
def Q2AV(Q):
    ''' convert quaternion to angle (radians 0-2pi) & normalized vector
        q=r+ai+bj+ck
    '''
    A = 2.*np.arccos(Q[0])
    V = np.array(Q[1:])
    V = V/np.sin(A/2.)
    return A,V
    
def randomQ(r0,r1,r2,r3):
    ''' create random quaternion from 4 random numbers in range (-1,1)
    '''
    sum = 0
    Q = np.array(4)
    Q[0] = r0
    sum += Q[0]**2
    Q[1] = np.sqrt(1.-sum)*r1
    sum += Q[1]**2
    Q[2] = np.sqrt(1.-sum)*r2
    sum += Q[2]**2
    Q[3] = np.sqrt(1.-sum)*np.where(r3<0.,-1.,1.)
    return Q
    
def randomAVdeg(r0,r1,r2,r3):
    ''' create random angle (deg),vector from 4 random number in range (-1,1)
    '''
    return Q2AVdeg(randomQ(r0,r1,r2,r3))
    
def makeQuat(A,B,C):
    ''' Make quaternion from rotation of A vector to B vector about C axis

        :param np.array A,B,C: Cartesian 3-vectors
        :returns: quaternion & rotation angle in radians q=r+ai+bj+ck
    '''

    V1 = np.cross(A,C)
    V2 = np.cross(B,C)
    if nl.norm(V1)*nl.norm(V2):
        V1 = V1/nl.norm(V1)
        V2 = V2/nl.norm(V2)
        V3 = np.cross(V1,V2)
    else:
        V3 = np.zeros(3)
    Q = np.array([0.,0.,0.,1.])
    D = 0.
    if nl.norm(V3):
        V3 = V3/nl.norm(V3)
        D1 = min(1.0,max(-1.0,np.vdot(V1,V2)))
        D = np.arccos(D1)/2.0
        V1 = C-V3
        V2 = C+V3
        DM = nl.norm(V1)
        DP = nl.norm(V2)
        S = np.sin(D)
        Q[0] = np.cos(D)
        Q[1:] = V3*S
        D *= 2.
        if DM > DP:
            D *= -1.
    return Q,D
    
def annealtests():
    from numpy import cos
    # minimum expected at ~-0.195
    func = lambda x: cos(14.5*x-0.3) + (x+0.2)*x
    print (anneal(func,1.0,full_output=1,upper=3.0,lower=-3.0,feps=1e-4,maxiter=2000,schedule='cauchy'))
    print (anneal(func,1.0,full_output=1,upper=3.0,lower=-3.0,feps=1e-4,maxiter=2000,schedule='fast'))
    print (anneal(func,1.0,full_output=1,upper=3.0,lower=-3.0,feps=1e-4,maxiter=2000,schedule='boltzmann'))

    # minimum expected at ~[-0.195, -0.1]
    func = lambda x: cos(14.5*x[0]-0.3) + (x[1]+0.2)*x[1] + (x[0]+0.2)*x[0]
    print (anneal(func,[1.0, 1.0],full_output=1,upper=[3.0, 3.0],lower=[-3.0, -3.0],feps=1e-4,maxiter=2000,schedule='cauchy'))
    print (anneal(func,[1.0, 1.0],full_output=1,upper=[3.0, 3.0],lower=[-3.0, -3.0],feps=1e-4,maxiter=2000,schedule='fast'))
    print (anneal(func,[1.0, 1.0],full_output=1,upper=[3.0, 3.0],lower=[-3.0, -3.0],feps=1e-4,maxiter=2000,schedule='boltzmann'))

if __name__ == '__main__':
    annealtests()
