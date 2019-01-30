###############################################################################
###
###     Copyright 2016 Autodesk Inc. All rights reserved.
###
###     Use of this software is subject to the terms of the Autodesk license
###     agreement provided at the time of installation or download, or which
###     otherwise accompanies this software in either electronic or hard copy form.
###
###############################################################################


import maya.cmds as cmds
import math

replaceShaders = True
targetShaders = ['VRayMtl', 'lambert', 'blinn', 'phong', 'mia_material_x_passes', 'mia_material_x', 'dielectric_material']
   

mappingVRMtl = [
            ['diffuseColorAmount', 'Kd'],
            ['color', 'color'],  #or diffuseColor ?
            ['roughnessAmount', 'diffuseRoughness'],            
            ['reflectionColorAmount', 'Ks'],
            ['reflectionColor', 'KsColor'],                   
            ['refractionColorAmount', 'Kt'],
            ['refractionColor', 'KtColor'],
            ['refractionIOR', 'IOR'],
            ['opacityMap', 'opacity'],
            ['useFresnel', 'specularFresnel'],
            ['anisotropyRotation', 'anisotropyRotation'],
            ['translucencyColor', 'KsssColor'],
            ['fogColor', 'transmittance'],
            ['fogColor', 'sssRadius'],
            ['normalCamera', 'normalCamera']  # or Bump ?
        ]


mappingLambert = [
            ['diffuse', 'Kd'],
            ['color', 'color'],
            ['normalCamera', 'normalCamera'],
            ['incandescence', 'emissionColor'],
            ['translucence', 'Kb']
        ]
        
mappingBlinn = [
            ['diffuse', 'Kd'],
            ['color', 'color'],
            ['specularRollOff', 'Ks'],
            ['specularColor', 'KsColor'],
            ['reflectivity', 'Kr'],
            ['reflectedColor', 'KrColor'],
            ['eccentricity', 'specularRoughness'],
            ['normalCamera', 'normalCamera'],
            ['incandescence', 'emissionColor'],
            ['transparency', 'opacity'],
            ['translucence', 'Kb']
        ]
                
mappingPhong = [
            ['diffuse', 'Kd'],
            ['color', 'color'],
            ['reflectedColor', 'KrColor'],
            ['specularColor', 'KsColor'],
            ['reflectivity', 'Kr'],
            ['normalCamera', 'normalCamera'],
            ['incandescence', 'emissionColor'],
            ['translucence', 'Kb']
        ]

mappingMia = [
            ['diffuse_weight', 'Kd'],
            ['diffuse', 'color'],
            ['diffuse_roughness', 'diffuseRoughness'],
            ['refl_color', 'KsColor'],
            ['reflectivity', 'Ks'],
            ['refr_ior', 'IOR'],
            ['refr_color', 'KtColor'],
            ['transparency', 'Kt'],
            ['anisotropy_rotation', 'anisotropyRotation'],
            ['cutout_opacity', 'opacity']
        ]
    

mappingDielectric = [
            ['ior', 'IOR'],
            ['col', 'transmittance']
        ]

    
def convertUi():
    ret = cmds.confirmDialog( title='Convert shaders', message='Convert all shaders in scene, or selected shaders?', button=['All', 'Selected', 'Cancel'], defaultButton='All', cancelButton='Cancel' )
    if ret == 'All':
        convertAllShaders()
    elif ret == 'Selected':
        convertSelection()
        
    setupOpacities()
    #convertOptions()

        
def convertSelection():
    """
    Loops through the selection and attempts to create arnold shaders on whatever it finds
    """
    
    sel = cmds.ls(sl=True)
    if sel:
        for s in sel:
            ret = doMapping(s)



def convertAllShaders():
    """
    Converts each (in-use) material in the scene
    """
    # better to loop over the types instead of calling
    # ls -type targetShader
    # if a shader in the list is not registered (i.e. VrayMtl)
    # everything would fail

    for shdType in targetShaders:
        shaderColl = cmds.ls(exactType=shdType)
        if shaderColl:
            for x in shaderColl:
                # query the objects assigned to the shader
                # only convert things with members
                shdGroup = cmds.listConnections(x, type="shadingEngine")
                setMem = cmds.sets( shdGroup, query=True )
                if setMem:
                    ret = doMapping(x)
        


def doMapping(inShd):
    """
    Figures out which attribute mapping to use, and does the thing.
    
    @param inShd: Shader name
    @type inShd: String
    """
    ret = None
    
    shaderType = cmds.objectType(inShd)
    if 'VRayMtl' in shaderType :
        ret = shaderToAiStandard(inShd, 'aiStandard', mappingVRMtl)
    
    elif 'lambert' in shaderType :
        ret = shaderToAiStandard(inShd, 'aiStandard', mappingLambert)
        convertLambert(inShd, ret)
    elif 'blinn' in shaderType :
        ret = shaderToAiStandard(inShd, 'aiStandard', mappingBlinn)
        convertBlinn(inShd, ret)
    elif 'phong' in shaderType :
        ret = shaderToAiStandard(inShd, 'aiStandard', mappingPhong)
        convertPhong(inShd, ret)
    elif 'mia_material_x_passes' in shaderType :
        ret = shaderToAiStandard(inShd, 'aiStandard', mappingMia)
        convertMia(inShd, ret)
    elif 'mia_material_x' in shaderType :
        ret = shaderToAiStandard(inShd, 'aiStandard', mappingMia)
        convertMia(inShd, ret)
    elif 'dielectric_material' in shaderType :
        ret = shaderToAiStandard(inShd, 'aiStandard', mappingDielectric)
        convertDielectric(inShd, ret)
    #else:
    #    print shaderType, " not supported yet"
    
        # do some cleanup on the roughness params
    #    for chan in ['specularRoughness', 'refractionRoughness']:
    #        conns = cmds.listConnections( ret + '.' + chan, d=False, s=True, plugs=True )
    #        if not conns:
    #            val = cmds.getAttr(ret + '.' + chan)
    #            setValue(ret + '.' + chan, (1 - val))
        
        
    if ret:
        # assign objects to the new shader
        assignToNewShader(inShd, ret)



def assignToNewShader(oldShd, newShd):
    """
    Creates a shading group for the new shader, and assigns members of the old shader to it
    
    @param oldShd: Old shader to upgrade
    @type oldShd: String
    @param newShd: New shader
    @type newShd: String
    """
    
    retVal = False
    
    shdGroup = cmds.listConnections(oldShd, type="shadingEngine")
    
    #print 'shdGroup:', shdGroup
    
    if shdGroup:
        if replaceShaders:
            cmds.connectAttr(newShd + '.outColor', shdGroup[0] + '.surfaceShader', force=True)
            cmds.delete(oldShd)
        else:
            cmds.connectAttr(newShd + '.outColor', shdGroup[0] + '.aiSurfaceShader', force=True)
        retVal =True
        
    return retVal


def setupConnections(inShd, fromAttr, outShd, toAttr):
    conns = cmds.listConnections( inShd + '.' + fromAttr, d=False, s=True, plugs=True )
    if conns:
        cmds.connectAttr(conns[0], outShd + '.' + toAttr, force=True)
        return True

    return False
                
            

def shaderToAiStandard(inShd, nodeType, mapping):
    """
    'Converts' a shader to arnold, using a mapping table.
    
    @param inShd: Shader to convert
    @type inShd: String
    @param nodeType: Arnold shader type to create
    @type nodeType: String
    @param mapping: List of attributes to map from old to new
    @type mapping: List
    """
    
    #print 'Converting material:', inShd
    
    if ':' in inShd:
        aiName = inShd.rsplit(':')[-1] + '_ai'
    else:
        aiName = inShd + '_ai'
        
    #print 'creating '+ aiName
    aiNode = cmds.shadingNode(nodeType, name=aiName, asShader=True)
    for chan in mapping:
        fromAttr = chan[0]
        toAttr = chan[1]
        
        if cmds.objExists(inShd + '.' + fromAttr):
            #print '\t', fromAttr, ' -> ', toAttr
            
            if not setupConnections(inShd, fromAttr, aiNode, toAttr):
                # copy the values
                val = cmds.getAttr(inShd + '.' + fromAttr)
                setValue(aiNode + '.' + toAttr, val)
    
    #print 'Done. New shader is ', aiNode
    
    return aiNode
        


def setValue(attr, value):
    """Simplified set attribute function.

    @param attr: Attribute to set. Type will be queried dynamically
    @param value: Value to set to. Should be compatible with the attr type.
    """

    aType = None

    if cmds.objExists(attr):
        # temporarily unlock the attribute
        isLocked = cmds.getAttr(attr, lock=True)
        if isLocked:
            cmds.setAttr(attr, lock=False)

        # one last check to see if we can write to it
        if cmds.getAttr(attr, settable=True):
            attrType = cmds.getAttr(attr, type=True)
            
            print value, type(value)
            
            if attrType in ['string']:
                aType = 'string'
                cmds.setAttr(attr, value, type=aType)
                
            elif attrType in ['long', 'short', 'float', 'byte', 'double', 'doubleAngle', 'doubleLinear', 'bool']:
                aType = None
                try:
                    cmds.setAttr(attr, value)
                except Exception as e:
                    print(e)
                
            elif attrType in ['long2', 'short2', 'float2',  'double2', 'long3', 'short3', 'float3',  'double3']:
                if isinstance(value, float):
                    if attrType in ['long2', 'short2', 'float2',  'double2']:
                        value = [(value,value)]
                    elif attrType in ['long3', 'short3', 'float3',  'double3']:
                        value = [(value, value, value)]

                try:
                    cmds.setAttr(attr, *value[0], type=attrType)
                except Exception as e:
                    print(e)
                
            #else:
            #    print 'cannot yet handle that data type!!'


        if isLocked:
            # restore the lock on the attr
            cmds.setAttr(attr, lock=True)


def transparencyToOpacity(inShd, outShd):
    transpMap = cmds.listConnections( inShd + '.transparency', d=False, s=True, plugs=True )
    if transpMap:
        # map is connected, argh...
        # need to add a reverse node in the shading tree

        # create reverse
        invertNode = cmds.shadingNode('reverse', name=outShd + '_rev', asUtility=True)

        #connect transparency Map to reverse 'input'
        cmds.connectAttr(transpMap[0], invertNode + '.input', force=True)

        #connect reverse to opacity
        cmds.connectAttr(invertNode + '.output', outShd + '.opacity', force=True)
    else:
        #print inShd

        transparency = cmds.getAttr(inShd + '.transparency')
        opacity = [(1.0 - transparency[0][0], 1.0 - transparency[0][1], 1.0 - transparency[0][2])]

        #print opacity
        setValue(outShd + '.opacity', opacity)


def convertLambert(inShd, outShd):        
    transparencyToOpacity(inShd, outShd)
    #print 'lambert'


def convertBlinn(inShd, outShd):        
    setValue(outShd + '.emission', 1.0)

    # Catch DeltaGen negative eccentricity values
    ecc = max(0.0, cmds.getAttr(inShd + '.eccentricity'))
    cmds.setAttr(inShd + '.eccentricity', ecc)

    transparencyToOpacity(inShd, outShd)    

def convertPhong(inShd, outShd): 
    cosinePower = cmds.getAttr(inShd + '.cosinePower')
    roughness = math.sqrt(1.0 / (0.454 * cosinePower + 3.357))
    setValue(outShd + '.specularRoughness', roughness)
    setValue(outShd + '.emission', 1.0)
    setValue(outShd + '.Ks', 1.0)
    transparencyToOpacity(inShd, outShd)

def convertMia(inShd, outShd):        
    
    val1 = cmds.getAttr(inShd + '.refl_gloss')
    setValue(outShd + '.specularRoughness', 1.0 - val1)
    if cmds.getAttr(inShd + '.refl_hl_only'):
        setValue(outShd + '.indirectSpecular', 0)

    if cmds.getAttr(inShd + '.refl_is_metal'):
        # need to multiply reflection color by diffuse Color
        if not cmds.listConnections( inShd + '.refl_is_metal', d=False, s=True, plugs=True ):
            #in case reflection Color has been used to attenuate reflections 
            # multiply reflectivity by one of its channels
            reflColor = cmds.getAttr(inShd + '.refl_color')
            reflIntensity = cmds.getAttr(inShd + '.reflectivity')
            reflIntensity *= reflColor[0]
            cmds.setAttr(outShd+'.Ks', reflIntensity)

        # assign specularColor to diffuse value
        if not setupConnections(inShd, 'diffuse', outShd, 'specularColor'):
            val = cmds.getAttr(inShd + '.diffuse')
            setValue(outShd + '.specularColor', val)
            
        
    val1 = cmds.getAttr(inShd + '.refr_gloss')
    setValue(outShd + '.refractionRoughness', 1.0 - val1)

    connOverallBump = cmds.listConnections( inShd + '.overall_bump', d=False, s=True, plugs=True )
    if connOverallBump:
        cmds.connectAttr(connOverallBump[0], outShd + '.normalCamera', force=True)
    else:
        connStandardBump = cmds.listConnections( inShd + '.standard_bump', d=False, s=True, plugs=True )
        if connStandardBump:
            cmds.connectAttr(connStandardBump[0], outShd + '.normalCamera', force=True)

    anisotropy = cmds.getAttr(inShd + '.anisotropy')
    if anisotropy > 1:
        #lerp from 1:10 to 0.5:1
        anisotropy = ((anisotropy - 1.0) * 0.5 / 9.0) + 0.5
        if anisotropy > 1:
            anisotropy = 1
    elif anisotropy < 1:
        #lerp from 0:1 to 0:0.5
        anisotropy = anisotropy * 0.5

    setValue(outShd+'.specularAnisotropy', anisotropy)
    setValue(outShd+'.specularFresnel', 1)

    ior_fresnel =  cmds.getAttr(inShd + '.brdf_fresnel')

    reflectivity = 1.0
    connReflectivity = cmds.listConnections( outShd + '.Ks', d=False, s=True, plugs=True )
    if not connReflectivity:
        reflectivity = cmds.getAttr(outShd+'.Ks')


    if ior_fresnel:
        # compute from IOR
        # using Schlick's approximation
        ior = cmds.getAttr(inShd + '.refr_ior')
        frontRefl = (ior - 1.0) / (ior + 1.0)
        frontRefl *= frontRefl
        setValue(outShd +'.Ksn', frontRefl * reflectivity)
    else:
        # ignoring brdf_90_degree_refl as it's usually left to 1
        setValue(outShd +'.Ksn', cmds.getAttr(inShd + '.brdf_0_degree_refl') * reflectivity)

    # copy translucency value only if refr_translucency is enabled
    if cmds.getAttr(inShd + '.refr_translucency'):
        setValue(outShd +'.Kb', cmds.getAttr(inShd + '.refr_trans_weight'))        

def convertDielectric(inShd, outShd):
    cosinePower = cmds.getAttr(inShd + '.phong_coef')
    ior = cmds.getAttr(inShd + '.ior')
    frontRefl = (ior - 1.0) / (ior + 1.0)
    frontRefl *= frontRefl

    if cosinePower > 0.0:
        roughness = math.sqrt(1.0 / (0.454 * cosinePower + 3.357))
        setValue(outShd + '.specularRoughness', roughness)
        setValue(outShd + '.Ks', 1.0)
        setValue(outShd + '.specularFresnel', 1)
        setValue(outShd + '.Ksn', frontRefl)

        #this "fake spec"  is only for direct illum
        setValue(outShd + '.indirectSpecular', 0)
        
    else:
        setValue(outShd + '.Ks', 0.0)


    setValue(outShd + '.Kd', 0.0)
    setValue(outShd + '.Kr', 1.0)
    setValue(outShd + '.Fresnel', 1)
    setValue(outShd + '.Krn', frontRefl)
    setValue(outShd + '.FresnelUseIOR', 1)
    setValue(outShd + '.Kt', 1.0)

def convertVrayMtl(inShd, outShd):

    #anisotropy from -1:1 to 0:1
    anisotropy = cmds.getAttr(inShd + '.anisotropy')
    anisotropy = (anisotropy * 2.0) + 1.0
    setValue(outShd + '.specularAnisotropy', anisotropy)

    # do we need to check lockFresnelIORToRefractionIOR 
    # or is fresnelIOR modified automatically when refractionIOR changes ?
    ior = 1.0
    if cmds.getAttr(inShd + '.lockFresnelIORToRefractionIOR'):
        ior = cmds.getAttr(inShd + '.refractionIOR')
    else:
        ior = cmds.getAttr(inShd + '.fresnelIOR')


    reflectivity = 1.0
    connReflectivity = cmds.listConnections( outShd + '.Ks', d=False, s=True, plugs=True )
    if not connReflectivity:
        reflectivity = cmds.getAttr(outShd+'.Ks')

    frontRefl = (ior - 1.0) / (ior + 1.0)
    frontRefl *= frontRefl

    setValue(outShd +'.Ksn', frontRefl * reflectivity)    
    
    reflGloss = cmds.getAttr(inShd + '.reflectionGlossiness')
    setValue(outShd + '.specularRoughness', 1.0 - reflGloss)

    refrGloss = cmds.getAttr(inShd + '.refractionGlossiness')
    setValue(outShd + '.refractionRoughness', 1.0 - refrGloss)
  

    #bumpMap, bumpMult, bumpMapType ?

    if cmds.getAttr(inShd + '.sssOn'):
        setValue(outShd + '.Ksss', 1.0)

    #selfIllumination is missing  but I need to know the exact attribute name in maya or this will fail


def convertOptions():
    cmds.setAttr("defaultArnoldRenderOptions.GIRefractionDepth", 10)
    

def isOpaque (shapeName):

    mySGs = cmds.listConnections(shapeName, type='shadingEngine')
    if not mySGs:
        return 1

    surfaceShader = cmds.listConnections(mySGs[0] + ".aiSurfaceShader")
    
    if surfaceShader == None:
        surfaceShader = cmds.listConnections(mySGs[0] + ".surfaceShader")

    if surfaceShader == None:
        return 1

    for shader in surfaceShader:
        if cmds.attributeQuery("opacity", node=shader, exists=True ) == 0:
            continue
    
        opacity = cmds.getAttr (shader + ".opacity")
        
        if opacity[0][0] < 1.0 or opacity[0][1] < 1.0 or opacity[0][2] < 1.0:
            return 0
        


    return 1


def setupOpacities():
    shapes = cmds.ls(type='geometryShape')
    for shape in shapes:       
        
        if isOpaque(shape) == 0:
            #print shape + ' is transparent'
            cmds.setAttr(shape+".aiOpaque", 0)  
        
            


if not cmds.pluginInfo( 'mtoa', query=True, loaded=True ):
    cmds.loadPlugin('mtoa')

convertUi()






