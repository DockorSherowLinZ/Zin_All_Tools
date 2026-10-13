"""3ds Max 2027: Scripting > Run Script > this file.
Keep max_routing_engine.py beside this script. No pip/install/network required.
Creates a layered editable demonstrator without resetting the current scene.
Replans from LIVE obstacle AABBs and connector transforms, creates native
Bezier splines, reads controls back and validates those actual controls.
Previous generations are archived by hiding, never deleted.
"""
import sys, json, csv, traceback, importlib, time
from pathlib import Path
from pymxs import runtime as rt
from PySide6 import QtWidgets, QtCore, QtGui
import qtmax

OUT=Path(rt.getDir(rt.Name('userScripts')))/'CableRoutingPoC'/'v1.3.2'/'exports'
OUT.mkdir(parents=True,exist_ok=True)
import types
engine=types.ModuleType('cable_routing_engine_v13')
exec(compile(__CR_ENGINE_SOURCE, '<CableRoutingEngine>', 'exec'), engine.__dict__)
sweep=types.ModuleType('cable_section_sweep_engine_v13')
exec(compile(__CR_SECTION_SOURCE, '<CableSectionSweep>', 'exec'), sweep.__dict__)
SCALE=float(rt.units.decodeValue('1mm'))
COLORS=[(35,205,240),(250,145,45),(130,230,95)]
LOG=OUT/'max_execution_log.txt'

def log(s):
    with LOG.open('a',encoding='utf-8') as f:f.write(time.strftime('%H:%M:%S')+' '+str(s)+'\n')

def p3(p):return rt.Point3(*(float(x)*SCALE for x in p))
def mm(p):return tuple(float(x)/SCALE for x in (p.x,p.y,p.z))
def xyz(p):return tuple(float(x) for x in (p.x,p.y,p.z))
def node(name):
    n=rt.getNodeByName(name)
    if n is None:raise ValueError('Missing scene object: '+name)
    return n
def nodes(role):return [n for n in rt.objects if rt.getUserProp(n,'CR_role')==role]
def tag(n,role):rt.setUserProp(n,'CR_role',role);return n
def layer(name):
    obj=rt.LayerManager.getLayerFromName(name)
    if obj is None:obj=rt.LayerManager.newLayerFromName(name)
    return obj
def material(name,color):return rt.StandardMaterial(name=name,diffuse=rt.Color(*color),specularLevel=25,glossiness=35)
def box(name,lo,hi,color,role='fixture'):
    o=rt.Box(name=name,width=(hi[0]-lo[0])*SCALE,length=(hi[1]-lo[1])*SCALE,height=(hi[2]-lo[2])*SCALE,pos=p3(((lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2])))
    o.wirecolor=rt.Color(*color);o.material=material(name+'_Mat',color);tag(o,role);layer('CR_Fixtures').addNode(o)
    return o
def text(body,pos,size=12,color=(220,230,240),name='CR_Label',role='label'):
    o=rt.Text(name=name,text=body,size=size*SCALE,pos=p3(pos))
    o.wirecolor=rt.Color(*color);tag(o,role);layer('CR_Labels').addNode(o)
    return o

def setup_scene():
    if rt.getNodeByName('CR_Port_A') is not None:return
    # No reset / no deletion / no change to system unit scale.
    rt.units.DisplayType=rt.Name('metric');rt.units.MetricType=rt.Name('millimeters')
    box('CR_Chassis_Floor',(0,0,-6),(600,400,0),(42,61,78))
    box('CR_Chassis_Rear',(0,400,0),(600,406,200),(48,68,86))
    box('CR_Chassis_Left',(-6,0,0),(0,400,200),(48,68,86))
    for i,(lo,hi) in enumerate([((230,130,0),(360,270,130)),((110,280,0),(190,350,110)),((410,50,0),(480,120,100))],1):
        box('CR_Obstacle_%02d'%i,lo,hi,(130,146,161),'obstacle')
    bounds=box('CR_Enclosure_Bounds',(0,0,0),(600,400,200),(45,60,70),'bounds')
    bounds.isHidden=True;bounds.renderable=False
    for key,center,port,rotation in [('A',(50,200,80),(60,200,80),0),('B',(550,200,80),(540,200,80),180)]:
        body=box('CR_Connector_'+key,(center[0]-10,center[1]-12,center[2]-12),(center[0]+10,center[1]+12,center[2]+12),(235,184,64),'connector')
        helper=rt.Point(name='CR_Port_'+key,pos=p3(port),size=8*SCALE,box=True,cross=True)
        helper.parent=body
        sign=1 if key=='A' else -1
        helper.transform=rt.Matrix3(rt.Point3(sign,0,0),rt.Point3(0,sign,0),rt.Point3(0,0,1),p3(port))
        helper.wirecolor=rt.Color(255,230,140);tag(helper,'port');layer('CR_Fixtures').addNode(helper)
        text(key,(center[0]-5,center[1]-8,center[2]+15),14,(255,220,135))
    text('CABLE ROUTING | 3ds Max',(0,-35,1),19)
    text('600 x 400 x 200 mm | A* + Bezier | move obstacles, then Replan',(0,-60,1),10)
    text('THREE ALTERNATIVES, NOT SIMULTANEOUS WIRES\nVERIFIED: native cubic controls / box clearance / bend bound / exit tangent\nNOT VERIFIED: physical cable / mesh contacts / assembly / wire-to-wire',(0,-185,1),9)
    cam=rt.FreeCamera(name='CR_Overview')
    eye=(950,-850,850);target=(300,110,50)
    z=engine.unit(engine.sub(eye,target));x=engine.unit(engine.cross((0,0,1),z));y=engine.cross(z,x)
    cam.transform=rt.Matrix3(rt.Point3(*x),rt.Point3(*y),rt.Point3(*z),p3(eye));cam.fov=40
    tag(cam,'camera');layer('CR_Cameras').addNode(cam)
    log('Scene created. mm scale='+str(SCALE))

rt.execute('''
fn CR_AddKnotWorld sh si kt st p iv ov = (in coordsys world (addKnot sh si kt st p iv ov))
fn CR_KnotWorld sh si ki = (in coordsys world (getKnotPoint sh si ki))
fn CR_InWorld sh si ki = (in coordsys world (getInVec sh si ki))
fn CR_OutWorld sh si ki = (in coordsys world (getOutVec sh si ki))
''')

def demo_scene_input():
    obstacles=nodes('obstacle')
    if not obstacles:raise ValueError('No tagged obstacle in scene')
    boxes=[];names=[]
    for o in obstacles:
        bb=rt.nodeGetBoundingBox(o,rt.Matrix3(1));boxes.append((mm(bb[0]),mm(bb[1])));names.append(str(o.name))
    bounds_node=node('CR_Enclosure_Bounds')
    # Axis-aligned enclosure only: do not falsely certify a rotated enclosure's AABB.
    for row,expected in [(bounds_node.transform.row1,(1,0,0)),(bounds_node.transform.row2,(0,1,0)),(bounds_node.transform.row3,(0,0,1))]:
        if engine.dot(engine.unit(xyz(row)),expected)<.999999:raise ValueError('Enclosure must remain axis-aligned')
    bb=rt.nodeGetBoundingBox(bounds_node,rt.Matrix3(1));bounds=(mm(bb[0]),mm(bb[1]))
    pa=node('CR_Port_A');pb=node('CR_Port_B')
    return dict(boxes=boxes,bounds=bounds,start=mm(pa.transform.row4),goal=mm(pb.transform.row4),start_dir=engine.unit(xyz(pa.transform.row1)),goal_out=engine.unit(xyz(pb.transform.row1))),names

def route_signature():
    out=[]
    for sh in nodes('route'):
        if not rt.getUserProp(sh,'CR_current'):continue
        knots=[]
        for i in range(1,int(rt.numKnots(sh,1))+1):
            knots.append([mm(rt.CR_KnotWorld(sh,1,i)),mm(rt.CR_InWorld(sh,1,i)),mm(rt.CR_OutWorld(sh,1,i))])
        out.append({'name':str(sh.name),'knots':knots,'diameter_mm':float(sh.render_thickness)/SCALE})
    return out

def create_spline(route,generation,diameter):
    seg=route['segments'];idx=route['route']
    sh=rt.SplineShape(name='CR_Alt_%d_G%02d'%(idx,generation));rt.addNewSpline(sh)
    for i in range(len(seg)+1):
        point=seg[i][0] if i<len(seg) else seg[-1][3]
        iv=seg[i-1][2] if i>0 else point
        ov=seg[i][1] if i<len(seg) else point
        rt.CR_AddKnotWorld(sh,1,rt.Name('bezierCorner'),rt.Name('curve'),p3(point),p3(iv),p3(ov))
    rt.updateShape(sh)
    sh.render_renderable=True;sh.render_displayRenderMesh=True;sh.render_useViewportSettings=False
    sh.render_thickness=diameter*SCALE;sh.render_sides=16;sh.steps=64;sh.optimize=False
    color=COLORS[idx-1] if route['metrics']['accepted'] else (255,65,75)
    sh.wirecolor=rt.Color(*color);sh.material=material(sh.name+'_Mat',color)
    tag(sh,'route');rt.setUserProp(sh,'CR_generation',generation);rt.setUserProp(sh,'CR_route_index',idx)
    layer('CR_Routes_G%02d'%generation).addNode(sh)
    actual=[]
    for i in range(1,len(seg)+1):
        actual.append((mm(rt.CR_KnotWorld(sh,1,i)),mm(rt.CR_OutWorld(sh,1,i)),mm(rt.CR_InWorld(sh,1,i+1)),mm(rt.CR_KnotWorld(sh,1,i+1))))
    error=max(engine.norm(engine.sub(a,b)) for planned,read in zip(seg,actual) for a,b in zip(planned,read))
    if error>.001:raise ValueError('Native spline control mismatch %.6f mm'%error)
    return sh,actual,error

def replan(parameters):
    live,names=scene_input();start=time.perf_counter()
    if isinstance(live['boxes'],selected_scene.SpatialBoxes):live['boxes'].cap=max(100.,parameters['diameter']/2+parameters['clearance']+parameters['grid']/2+30.)
    report=engine.plan(**live,**parameters);report['obstacle_names']=names
    old_routes=nodes('route');generation=max([int(rt.getUserProp(n,'CR_generation') or 0) for n in old_routes]+[0])+1
    created=[]
    # Do all planning first. Preserve previous generation if a scene API fails.
    for route in report['routes']:
        if not route['segments']:continue
        sh,actual,error=create_spline(route,generation,parameters['diameter']);created.append(sh)
        verified=engine.certify(actual,live['boxes'],live['bounds'],parameters['diameter']/2,parameters['clearance'],parameters['bend'],live['start'],live['goal'],live['start_dir'],live['goal_out'],parameters['stub'])
        verified['native_control_error_mm']=error;verified['native_readback_verified']=True
        route['metrics']=verified;route['segments']=actual;route['node_name']=str(sh.name)
        for k,v in verified.items():
            if v is not None:rt.setUserProp(sh,'CR_'+k,v)
        if not verified['accepted']:sh.wirecolor=rt.Color(255,65,75);sh.material.diffuse=rt.Color(255,65,75)
    passed=[r for r in report['routes'] if r['metrics']['accepted']]
    report['recommended_route']=min(passed,key=lambda r:r['metrics']['length_mm'])['route'] if passed else None
    for n in old_routes:n.isHidden=True;rt.setUserProp(n,'CR_current',False)
    for n in nodes('result_label'):n.isHidden=True
    for n in created:rt.setUserProp(n,'CR_current',True)
    for route in report['routes']:
        m=route['metrics'];i=route['route']
        if 'length_mm' in m:
            body='ALT %d | L %.1f mm | gap >= %.1f | R >= %.1f | %s'%(i,m['length_mm'],m['clearance_lower_mm'],m['radius_lower_mm'] or 99999,m['status'])
        else:body='ALT %d | NO PATH AT THIS GRID / MARGIN'%i
        text(body,(0,-85-(i-1)*23,1),10,COLORS[i-1] if m['accepted'] else (255,80,80),name='CR_Result_%d_G%d'%(i,generation),role='result_label')
    report['elapsed_seconds']=time.perf_counter()-start;report['generation']=generation
    report['scene_signature']=live;report['route_signature']=route_signature()
    report['max_version']=str(rt.maxVersion());report['mm_to_system_unit']=SCALE
    rt.redrawViews();write_report(report)
    log('Replan generation %d: %s'%(generation,[(r['route'],r['metrics']['status']) for r in report['routes']]))
    return report

def write_report(report):
    (OUT/'max_routing_metrics.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    fields=['route','status','accepted','length_mm','length_lower_mm','length_upper_mm','clearance_lower_mm','radius_lower_mm','exit_tangent_pass','straight_lead_pass','native_control_error_mm']
    with (OUT/'max_routing_metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for r in report['routes']:writer.writerow(dict(route=r['route'],**r['metrics']))

def overview():
    try:
        node('CR_Overview').fov=40
        rt.viewport.setCamera(node('CR_Overview'));rt.redrawViews()
    except Exception:log('Overview camera: '+traceback.format_exc())

def capture():
    try:
        rt.completeRedraw();bm=rt.gw.getViewportDib();bm.filename=str(OUT/'max_cable_routing_preview.png');rt.save(bm);rt.close(bm)
        log('Viewport preview saved')
    except Exception:log('Preview: '+traceback.format_exc())

def save_scene():
    ok=rt.saveMaxFile(str(OUT/'max_cable_routing.max'),quiet=True)
    if not ok:raise IOError('3ds Max save failed')
    log('MAX scene saved')

import hashlib, base64
LIB=OUT.parent/'connector_library'
CATALOG=json.loads((LIB/'catalog.json').read_text(encoding='utf-8'))

def connector_asset(asset_id, endpoint):
    asset=next(a for a in CATALOG['assets'] if a['id']==asset_id)
    path=LIB/asset['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=asset['fbx_sha256']:
        raise ValueError('Connector asset checksum mismatch')
    port=node('CR_Port_'+endpoint)
    before={int(rt.getHandleByAnim(n)) for n in rt.objects}
    rt.FBXImporterSetParam('PushSettings')
    try:
        rt.FBXImporterSetParam('Mode',rt.Name('create'))
        if not rt.importFile(str(path),rt.Name('noPrompt'),using=rt.FBXIMP):raise ValueError('FBX import failed')
    finally:rt.FBXImporterSetParam('PopSettings')
    imported=[n for n in rt.objects if int(rt.getHandleByAnim(n)) not in before]
    meshes=[n for n in imported if rt.canConvertTo(n,rt.Editable_Mesh)]
    if len(meshes)!=asset['mesh_count']:raise ValueError('Asset mesh count mismatch')
    faces=sum(int(rt.getNumFaces(rt.snapshotAsMesh(n))) for n in meshes)
    if faces!=asset['faces']:raise ValueError('Asset face count mismatch')
    matrices=[n.transform*asset_calibration(asset)*port.transform for n in meshes]
    previous=[n for n in nodes('connector_model') if rt.getUserProp(n,'CR_endpoint')==endpoint]
    for i,(n,matrix) in enumerate(zip(meshes,matrices)):
        n.parent=port;n.transform=matrix;n.name='CR_Model_'+endpoint+'_'+asset_id+'_'+str(i+1)
        tag(n,'connector_model');rt.setUserProp(n,'CR_endpoint',endpoint)
        rt.setUserProp(n,'CR_asset_id',asset_id);rt.setUserProp(n,'CR_current_model',True)
        layer('CR_Connector_Models').addNode(n);store_model_exit(n,port)
    for n in previous:n.isHidden=True;rt.setUserProp(n,'CR_current_model',False)
    for n in imported:
        if n not in meshes:n.isHidden=True
    node('CR_Connector_'+endpoint).isHidden=True
    rt.setUserProp(port,'CR_asset_id',asset_id)
    rt.setUserProp(port,'CR_datum_status','CAD_RIBBON_END_FACE' if asset.get('cable_exit') else 'PROVISIONAL_BBOX')
    rt.setUserProp(port,'CR_exit_version','1.3.2')
    rt.redrawViews()
    return {'asset_id':asset_id,'endpoint':endpoint,'mesh_count':len(meshes),'faces':faces,'datum_verified':False}

def set_routing_anchor(endpoint):
    selected=list(rt.selection)
    if len(selected)!=1:raise ValueError('請選取一個定位輔助物件；其本地 +X 為出線方向')
    source=selected[0];port=node('CR_Port_'+endpoint)
    if source==port:raise ValueError('請選取另一個定位輔助物件')
    rows=[xyz(source.transform.row1),xyz(source.transform.row2),xyz(source.transform.row3)]
    if any(abs(engine.norm(row)-1)>1e-5 for row in rows) or any(abs(engine.dot(rows[i],rows[j]))>1e-5 for i,j in ((0,1),(0,2),(1,2))) or engine.dot(engine.cross(rows[0],rows[1]),rows[2])<.99999:
        raise ValueError('定位物件必須無縮放、無鏡射、無斜切')
    children=[(n,n.transform) for n in nodes('connector_model') if n.parent==port]
    port.transform=source.transform
    # Recalibrate routing reference while keeping imported mesh stationary.
    for n,matrix in children:n.transform=matrix
    rt.setUserProp(port,'CR_datum_status','USER_DEFINED_UNVERIFIED')
    rt.redrawViews()

def cable_metadata(panel):
    data={'version':'1.3.2','name':panel.cable_type.currentText(),
          'nominal_length_mm':panel.nominal.value() or None,'awg':panel.awg.text().strip() or None,
          'linear_mass_kg_per_m':panel.mass.value() or None,'bending_stiffness_N_m2':panel.stiffness.value() or None,
          'source':'user_input','physics_calibrated':False,'physics_simulated':False,
          'connectors':{}}
    for endpoint in ('A','B'):
        port=node('CR_Port_'+endpoint)
        data['connectors'][endpoint]={'asset_id':rt.getUserProp(port,'CR_asset_id') or 'placeholder','datum_status':rt.getUserProp(port,'CR_datum_status') or 'DEMO','datum_verified':False}
        data['connectors'][endpoint]['join_check']=connector_join_status(endpoint)
    data['cross_section']=section_definition(panel)
    data['scene_scope']=port_prop('CR_Port_A','CR_scene_scope') or 'tagged'
    for endpoint in ('A','B'):
        data['connectors'][endpoint]['scene_source']=port_prop('CR_Port_'+endpoint,'CR_source_name')
    return data

def attach_cable_metadata(panel):
    data=cable_metadata(panel);panel.report['cable_specification']=data
    nominal=data['nominal_length_mm']
    for route in panel.report['routes']:
        metrics=route['metrics'];length=metrics.get('length_mm')
        route['nominal_length_margin_mm']=nominal-length if nominal and length is not None else None
        route['nominal_length_sufficient']=(length<=nominal) if nominal and length is not None else None
    encoded=json.dumps(data,ensure_ascii=True)
    for n in nodes('route'):
        if rt.getUserProp(n,'CR_current'):rt.setUserProp(n,'CR_cable_specification',encoded)
    rt.setUserProp(node('CR_Port_A'),'CR_panel_state',json.dumps({'parameters':panel.parameters(),'specification':data},ensure_ascii=True))
    write_report(panel.report)

def restore_panel_state(panel):
    encoded=port_prop('CR_Port_A','CR_panel_state')
    if not encoded:return
    try:
        state=json.loads(encoded)
        for key,value in state['parameters'].items():
            if key in panel.inputs:panel.inputs[key].setValue(value)
        spec=state['specification'];panel.cable_type.setCurrentText(spec['name'])
        panel.nominal.setValue(spec.get('nominal_length_mm') or 0);panel.awg.setText(spec.get('awg') or '')
        panel.mass.setValue(spec.get('linear_mass_kg_per_m') or 0);panel.stiffness.setValue(spec.get('bending_stiffness_N_m2') or 0)
    except Exception:log('Saved panel state could not be restored: '+traceback.format_exc())

def add_connector_ui(panel,layout):
    group=CollapsibleSection('接頭模型庫與線材規格 | v1.3.2');form=QtWidgets.QFormLayout(group.body)
    panel.endpoint=QtWidgets.QComboBox();panel.endpoint.addItems(['A','B'])
    panel.asset=QtWidgets.QComboBox()
    for asset in CATALOG['assets']:panel.asset.addItem(asset['label'],asset['id'])
    row=QtWidgets.QHBoxLayout();row.addWidget(panel.endpoint);row.addWidget(panel.asset)
    apply=QtWidgets.QPushButton('替換接頭');row.addWidget(apply);form.addRow('目標端',row)
    anchor=QtWidgets.QPushButton('用所選輔助物件校正出線基準（+X）');form.addRow(anchor)
    panel.cable_type=QtWidgets.QComboBox();panel.cable_type.setEditable(True)
    panel.cable_type.addItems(['自訂 Cable','MCIO Cable','2x4-pin Power Cable','Slimline Cable','HDD Cable（規格待填）','CPU Power Cable（規格待填）','44PIN（定義待確認）','38x2PIN（定義待確認）'])
    form.addRow('Cable 名稱',panel.cable_type)
    panel.nominal=QtWidgets.QDoubleSpinBox();panel.nominal.setRange(0,100000);panel.nominal.setSuffix(' mm');panel.nominal.setSpecialValueText('未指定')
    form.addRow('可用線長',panel.nominal)
    panel.awg=QtWidgets.QLineEdit();panel.awg.setPlaceholderText('AWG 或自訂規格；不推定端子相容性');form.addRow('導體規格',panel.awg)
    panel.mass=QtWidgets.QDoubleSpinBox();panel.mass.setDecimals(6);panel.mass.setRange(0,100);panel.mass.setSpecialValueText('未知');panel.mass.setSuffix(' kg/m');form.addRow('線密度（僅記錄）',panel.mass)
    panel.stiffness=QtWidgets.QDoubleSpinBox();panel.stiffness.setDecimals(6);panel.stiffness.setRange(0,10000);panel.stiffness.setSpecialValueText('未知');panel.stiffness.setSuffix(' N m²');form.addRow('彎曲剛度 EI（僅記錄）',panel.stiffness)
    note=QtWidgets.QLabel('MCIO 的出線方向與截面取自 CAD；裝配基準仍待確認。\n其餘接頭基準暫定。物理欄位僅記錄資料。')
    note.setWordWrap(True);form.addRow(note);layout.addWidget(group)
    def replace():
        try:
            connector_asset(panel.asset.currentData(),panel.endpoint.currentText())
            if panel.asset.currentData()=='cable-mcio-x8-74pin-tab-ve':panel.section.setCurrentIndex(panel.section.findData('mcio_cad_dual_ribbon'))
            panel.mark_stale()
            panel.status.setText('接頭已替換；MCIO 使用 CAD 出線端面，其餘基準暫定。請重新規劃。')
        except Exception:panel.status.setText('替換失敗：'+traceback.format_exc().splitlines()[-1]);log(traceback.format_exc())
    def calibrate():
        try:
            set_routing_anchor(panel.endpoint.currentText());panel.mark_stale();panel.status.setText('已設定使用者基準，模型位置保留；請重新規劃。')
        except Exception:panel.status.setText(traceback.format_exc().splitlines()[-1])
    apply.clicked.connect(replace);anchor.clicked.connect(calibrate)
    for control in (panel.nominal,panel.mass,panel.stiffness):control.valueChanged.connect(panel.mark_stale)
    panel.awg.textChanged.connect(panel.mark_stale);panel.cable_type.currentTextChanged.connect(panel.mark_stale)


import math,struct

def asset_calibration(asset):
    rows=asset.get('asset_to_port_rows')
    if not rows:return rt.Matrix3(1)
    return rt.Matrix3(rt.Point3(*rows[0]),rt.Point3(*rows[1]),rt.Point3(*rows[2]),p3(rows[3]))

def store_model_exit(n,port):
    inv=rt.inverse(n.transform)
    points=[rt.Point3(0,0,0),rt.Point3(SCALE,0,0),rt.Point3(0,SCALE,0)]
    local=[xyz(p*port.transform*inv) for p in points]
    rt.setUserProp(n,'CR_model_exit_local',json.dumps(local))

def connector_join_status(endpoint):
    port=node('CR_Port_'+endpoint);asset_id=rt.getUserProp(port,'CR_asset_id')
    asset=next((a for a in CATALOG['assets'] if a['id']==asset_id),{})
    models=[n for n in nodes('connector_model') if rt.getUserProp(n,'CR_endpoint')==endpoint and rt.getUserProp(n,'CR_current_model')]
    if not asset.get('cable_exit') or not models:return {'verified':False,'reason':'此接頭尚無 CAD 出線截面基準'}
    errors=[];angles=[];widths=[]
    for n in models:
        encoded=rt.getUserProp(n,'CR_model_exit_local')
        if not encoded:return {'verified':False,'reason':'需重新套用 v1.2 接頭模型'}
        points=[mm(rt.Point3(*p)*n.transform) for p in json.loads(encoded)]
        direction=engine.unit(engine.sub(points[1],points[0]));width=engine.unit(engine.sub(points[2],points[0]))
        errors.append(engine.norm(engine.sub(points[0],mm(port.transform.row4))))
        angles.append(engine.dot(direction,engine.unit(xyz(port.transform.row1))))
        widths.append(engine.dot(width,engine.unit(xyz(port.transform.row2))))
    return {'verified':max(errors)<.001 and min(angles)>.99999 and min(widths)>.99999,'origin_error_mm':max(errors),'direction_dot':min(angles),'width_axis_dot':min(widths),'geometry_source':'CAD ribbon end face','engineering_verified':False}

def section_definition(panel):
    mode=panel.section.currentData()
    if mode=='mcio_raw_ribbon':
        w,h=27.30,.85
        data={'mode':mode,'id':'mcio_30awg_12pair_raw_proxy','contours_mm':[[[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]]],
              'geometry_source':'Amphenol MCIO 30 AWG 12-pair raw ribbon proxy',
              'width_mm':w,'total_thickness_mm':h,'reference_bend_mm':2.125,'engineering_verified':False,
              'source_url':'https://www.amphenol-ast.com/V3/UpLoadFiles/20180724/2018072415341140.pdf','finished_sleeve_included':False}
    elif mode=='mcio_cad_dual_ribbon':
        data=dict(CATALOG['profiles'][0]);data['mode']=mode
    elif mode=='rectangle':
        w=panel.section_width.value();h=panel.section_thickness.value()
        data={'mode':mode,'id':'user_rectangle','contours_mm':[[[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]]],'geometry_source':'User-entered rectangle','width_mm':w,'total_thickness_mm':h,'engineering_verified':False}
    else:
        d=panel.inputs['diameter'].value()
        data={'mode':'circle','id':'user_circle','contours_mm':[[[d/2*math.cos(i*2*math.pi/32),d/2*math.sin(i*2*math.pi/32)] for i in range(32)]],'geometry_source':'User-entered circle','width_mm':d,'total_thickness_mm':d,'engineering_verified':False}
    data['enclosing_radius_mm']=max(math.hypot(*p) for poly in data['contours_mm'] for p in poly)
    data['mesh_chord_allowance_mm']=.02
    data['planning_diameter_mm']=2*(data['enclosing_radius_mm']+.02)
    return data

def section_parameters(panel):
    values={k:v.value() for k,v in panel.inputs.items()}
    values['diameter']=section_definition(panel)['planning_diameter_mm']
    return values

def add_section_ui(panel,layout):
    group=CollapsibleSection('Cable 截面與端面方向');form=QtWidgets.QFormLayout(group.body)
    panel.section=QtWidgets.QComboBox()
    for label,mode in [('MCIO 30AWG 扁平 27.30 × 0.85 mm（代理規格）','mcio_raw_ribbon'),('MCIO CAD 雙層扁平截面','mcio_cad_dual_ribbon'),('自訂扁平矩形','rectangle'),('自訂圓形','circle')]:panel.section.addItem(label,mode)
    if not any(port_prop('CR_Port_'+endpoint,'CR_asset_id')=='cable-mcio-x8-74pin-tab-ve' for endpoint in ('A','B')):panel.section.setCurrentIndex(panel.section.findData('circle'))
    if port_prop('CR_Port_A','CR_scene_scope')=='all_scene':panel.section.setCurrentIndex(panel.section.findData('mcio_raw_ribbon'))
    panel.section_width=QtWidgets.QDoubleSpinBox();panel.section_width.setRange(.1,100);panel.section_width.setValue(20);panel.section_width.setSuffix(' mm')
    panel.section_thickness=QtWidgets.QDoubleSpinBox();panel.section_thickness.setRange(.1,30);panel.section_thickness.setValue(2.05);panel.section_thickness.setDecimals(3);panel.section_thickness.setSuffix(' mm')
    form.addRow('截面',panel.section);row=QtWidgets.QHBoxLayout();row.addWidget(panel.section_width);row.addWidget(panel.section_thickness);form.addRow('寬度／總厚度',row)
    note=QtWidgets.QLabel('MCIO CAD：20 mm × 兩層 1 mm；原始扁平線材代理：27.30 × 0.85 mm。\n代理截面不含套管，尚未配對線材料號；採包絡半徑保守避障。');note.setWordWrap(True);form.addRow(note);layout.addWidget(group)
    panel._round_diameter=6;panel._section_updating=False;panel._profile_mode=None
    def update(*_):
        if panel._section_updating:return
        panel._section_updating=True
        try:
            mode=panel.section.currentData()
            if panel._profile_mode=='circle' and mode!='circle':panel._round_diameter=panel.inputs['diameter'].value()
            if mode=='circle' and panel._profile_mode!='circle':panel.inputs['diameter'].setValue(panel._round_diameter)
            panel.section_width.setEnabled(mode=='rectangle');panel.section_thickness.setEnabled(mode=='rectangle');panel.inputs['diameter'].setEnabled(mode=='circle')
            if mode=='mcio_cad_dual_ribbon':panel.section_width.setValue(20);panel.section_thickness.setValue(2.05)
            if mode=='mcio_raw_ribbon':panel.section_width.setValue(27.30);panel.section_thickness.setValue(.85)
            if mode!='circle':panel.inputs['diameter'].setValue(section_definition(panel)['planning_diameter_mm'])
            panel._profile_mode=mode;panel.mark_stale()
        finally:panel._section_updating=False
    panel._update_section=update
    panel.section.currentIndexChanged.connect(update);panel.section_width.valueChanged.connect(update);panel.section_thickness.valueChanged.connect(update);update()

def restore_section_state(panel):
    encoded=port_prop('CR_Port_A','CR_panel_state')
    if not encoded:return
    try:
        spec=json.loads(encoded)['specification'];section=spec.get('cross_section')
        if section:
            panel.section.setCurrentIndex(panel.section.findData(section['mode']))
            if section['mode']=='rectangle':panel.section_width.setValue(section['width_mm']);panel.section_thickness.setValue(section['total_thickness_mm'])
            if section['mode']=='circle':panel.inputs['diameter'].setValue(section['width_mm'])
    except Exception:log(traceback.format_exc())

def sweep_signature():
    result=[]
    for n in nodes('route_mesh'):
        if not rt.getUserProp(n,'CR_current'):continue
        mesh=rt.snapshotAsMesh(n);verts=rt.meshop.getVerts(mesh,rt.Name('all'));digest=hashlib.sha256()
        for p in verts:digest.update(struct.pack('<fff',float(p.x),float(p.y),float(p.z)))
        result.append([str(n.name),len(verts),int(rt.getNumFaces(mesh)),digest.hexdigest()])
    return result

def attach_section_meshes(panel):
    definition=section_definition(panel);joins={k:connector_join_status(k) for k in ('A','B')}
    required=definition['mode']=='mcio_cad_dual_ribbon';join_pass=all(j['verified'] for j in joins.values()) if required else None
    old=[n for n in nodes('route_mesh') if rt.getUserProp(n,'CR_current')];created=[]
    for route in panel.report['routes']:
        if not route.get('segments'):continue
        curve=node(route['node_name']);curve.render_renderable=False;curve.render_displayRenderMesh=False
        data=sweep.build(route['segments'],definition['contours_mm'],xyz(node('CR_Port_A').transform.row2),xyz(node('CR_Port_B').transform.row2),panel.inputs['stub'].value(),tolerance=.02)
        mesh=rt.mesh(name='CR_Section_Alt_%d_G%02d'%(route['route'],panel.report['generation']),vertices=rt.Array(*[p3(p) for p in data['vertices']]),faces=rt.Array(*[rt.Point3(a+1,b+1,c+1) for a,b,c in data['faces']]))
        mesh.material=curve.material;mesh.wirecolor=curve.wirecolor;tag(mesh,'route_mesh');rt.setUserProp(mesh,'CR_current',True);rt.setUserProp(mesh,'CR_generation',panel.report['generation']);layer('CR_Routes_G%02d'%panel.report['generation']).addNode(mesh);created.append(mesh)
        # Read back the actual native mesh. Snapshot is already in world space.
        read=rt.meshop.getVerts(rt.snapshotAsMesh(mesh),rt.Name('all'))
        error=max(engine.norm(engine.sub(mm(p),expected)) for p,expected in zip(read,data['vertices']))
        if len(read)!=len(data['vertices']) or error>.001:raise ValueError('Native section mesh readback mismatch')
        metrics=data['metrics'];metrics['native_vertex_error_mm']=error;metrics['native_readback_verified']=True
        route['sweep_mesh']={'node_name':str(mesh.name),'metrics':metrics,'start_ring_vertex_indices':data['ring_indices'][0][0],'end_ring_vertex_indices':data['ring_indices'][0][-1]}
        route['geometry_accepted']=route['metrics']['accepted'];route['cad_join_pass']=join_pass
        if required and not join_pass:
            route['metrics']['accepted']=False;route['metrics']['status']='JOIN UNVERIFIED';mesh.wirecolor=rt.Color(255,100,65)
        rt.setUserProp(mesh,'CR_cross_section',json.dumps(definition,ensure_ascii=True))
    for n in old:n.isHidden=True;rt.setUserProp(n,'CR_current',False)
    panel.report['physical_route_validated']=False
    panel.report['endpoint_cad_exit_calibrated']=all(port_prop('CR_Port_'+k,'CR_datum_status')=='CAD_RIBBON_END_FACE' for k in ('A','B'))
    panel.report['scene_scope']=port_prop('CR_Port_A','CR_scene_scope') or 'tagged'
    panel.report['cross_section']=definition;panel.report['connector_join_checks']=joins;panel.report['sweep_signature']=sweep_signature()
    passed=[r for r in panel.report['routes'] if r['metrics']['accepted']]
    panel.report['recommended_route']=min(passed,key=lambda r:r['metrics']['length_mm'])['route'] if passed else None
    panel.report['validation_scope']+='; configured section polygon mesh with native vertex readback and closed manifold topology; enclosing radius + chord error used for conservative clearance.'
    panel.report['not_verified']=[s for s in panel.report['not_verified'] if s!='rendered tube mesh']+['sweep self-intersection, torsional strain and physical flat-cable bending','non-MCIO cable exit datums and connector-specific custom sections']
    for label in nodes('result_label'):
        if not label.isHidden:label.text=str(label.text)+' | '+definition['id']+(' | JOIN UNVERIFIED' if required and not join_pass else '')

def upgrade_mcio_connectors():
    # Explicit version migration, retaining archived prior meshes.
    for endpoint in ('A','B'):
        port=node('CR_Port_'+endpoint)
        if rt.getUserProp(port,'CR_asset_id')=='cable-mcio-x8-74pin-tab-ve' and rt.getUserProp(port,'CR_exit_version')!='1.3.2':connector_asset('cable-mcio-x8-74pin-tab-ve',endpoint)


selected_scene=types.ModuleType('cable_selected_scene_v13')
exec(compile(__CR_SELECTED_SOURCE, '<SelectedSceneTools>', 'exec'), selected_scene.__dict__)

_old_surface_gap=engine.surface_gap
def _indexed_gap(p,boxes,bounds,radius):
    if not isinstance(boxes,selected_scene.SpatialBoxes):return _old_surface_gap(p,boxes,bounds,radius)
    lo,hi=bounds
    wall=min(min(p[i]-lo[i],hi[i]-p[i]) for i in range(3))
    return min(wall,boxes.distance(p))-radius
engine.surface_gap=_indexed_gap

def ensure_scene_helpers():
    for endpoint in ('A','B'):
        if rt.getNodeByName('CR_Port_'+endpoint) is None:
            obj=rt.Point(name='CR_Port_'+endpoint,size=8*SCALE,box=True,cross=True)
            tag(obj,'port');layer('CR_Fixtures').addNode(obj)
            rt.setUserProp(obj,'CR_datum_status','UNASSIGNED')
    if rt.getNodeByName('CR_Enclosure_Bounds') is None:
        b=box('CR_Enclosure_Bounds',(0,0,0),(1,1,1),(45,60,70),'bounds')
        b.isHidden=True;b.renderable=False

def scene_external_meshes():
    ignored={'port','bounds','route','route_mesh','result_label','label','camera','connector','connector_model','preview_mesh'}
    return [n for n in rt.objects if rt.getUserProp(n,'CR_role') not in ignored and not rt.isGroupHead(n) and rt.canConvertTo(n,rt.Editable_Mesh)]

def selected_roots():
    chosen=list(rt.selection);handles={int(rt.getHandleByAnim(n)) for n in chosen};roots=[]
    for n in chosen:
        parent=n.parent;nested=False
        while parent is not None:
            if int(rt.getHandleByAnim(parent)) in handles:nested=True;break
            parent=parent.parent
        if not nested:roots.append(n)
    return roots

def source_node(endpoint):
    handle=port_prop('CR_Port_'+endpoint,'CR_source_handle')
    if not handle:return None
    for n in rt.objects:
        if int(rt.getHandleByAnim(n))==int(handle):return n
    raise ValueError('接頭來源已不存在；請重新設定端點 '+endpoint)

def source_family(endpoint):
    source=source_node(endpoint)
    if source is None:return set()
    result=set();todo=[source]
    while todo:
        n=todo.pop();result.add(int(rt.getHandleByAnim(n)));todo.extend(list(n.children))
    return result

def connector_bounds(source):
    bounds=[];todo=[source]
    while todo:
        obj=todo.pop();todo.extend(list(obj.children))
        if rt.getUserProp(obj,'CR_role') or rt.isGroupHead(obj) or not rt.canConvertTo(obj,rt.Editable_Mesh):continue
        bb=rt.nodeGetBoundingBox(obj,rt.Matrix3(1));bounds.append((mm(bb[0]),mm(bb[1])))
        if len(bounds)>100:raise ValueError('所選組立包含過多零件；請只選接頭，勿選整機或主板')
    if not bounds:raise ValueError('所選接頭沒有可用的網格；請選接頭組立或實際網格')
    return tuple(min(x[0][i] for x in bounds) for i in range(3)),tuple(max(x[1][i] for x in bounds) for i in range(3))

def bind_scene_connector(panel,endpoint,source):
    if rt.getUserProp(source,'CR_role') in ('port','bounds','route','route_mesh','preview_mesh'):
        raise ValueError('請選取實際接頭模型，不要選取 PoC 輔助物件')
    ensure_scene_helpers()
    rt.setUserProp(node('CR_Port_A'),'CR_scene_scope',panel.scene_scope.currentData())
    own=int(rt.getHandleByAnim(source));other='B' if endpoint=='A' else 'A'
    other_handle=port_prop('CR_Port_'+other,'CR_source_handle')
    if other_handle and own==int(other_handle):raise ValueError('A、B 必須是不同接頭')
    mode=panel.exit_axes[endpoint].currentData();basis,axis,sign=mode.split(':');axis=int(axis);sign=int(sign)
    direction=[0.,0.,0.];direction[axis]=sign
    preferred=(0.,0.,1.)
    if basis=='local':
        rows=[xyz(source.transform.row1),xyz(source.transform.row2),xyz(source.transform.row3)]
        direction=engine.mul(rows[axis],sign);preferred=rows[(axis+1)%3]
    bounds=connector_bounds(source)
    if max(bounds[1][i]-bounds[0][i] for i in range(3))<1e-6:raise ValueError('所選物件沒有有效接頭尺寸')
    if max(bounds[1][i]-bounds[0][i] for i in range(3))>200:raise ValueError('所選組立超過 200 mm；請只選接頭，勿選整機或主板')
    point,rows=selected_scene.bbox_exit(bounds,direction,preferred)
    port=node('CR_Port_'+endpoint)
    port.parent=source
    port.transform=rt.Matrix3(rt.Point3(*rows[0]),rt.Point3(*rows[1]),rt.Point3(*rows[2]),p3(point))
    for key,value in [('CR_source_handle',own),('CR_source_name',str(source.name)),('CR_exit_axis',mode),
                      ('CR_asset_id','scene_connector'),('CR_datum_status','BBOX_FACE_ASSUMED'),('CR_exit_version','1.3.2')]:
        rt.setUserProp(port,key,value)
    # Only old PoC placeholders are archived. The selected CAD model is retained.
    placeholder=rt.getNodeByName('CR_Connector_'+endpoint)
    if placeholder is not None:placeholder.isHidden=True
    for obj in nodes('connector_model'):
        if rt.getUserProp(obj,'CR_endpoint')==endpoint:
            obj.isHidden=True;rt.setUserProp(obj,'CR_current_model',False)
    panel.mark_stale();rt.redrawViews()

def scene_input():
    if any(rt.getNodeByName('CR_Port_'+k) is None for k in ('A','B')):raise ValueError('請先設定 A、B 接頭')
    mode=port_prop('CR_Port_A','CR_scene_scope') or 'all_scene'
    if mode!='all_scene':return demo_scene_input()
    for endpoint in ('A','B'):
        if port_prop('CR_Port_'+endpoint,'CR_datum_status')=='UNASSIGNED':
            raise ValueError('請先設定 A、B 端點；目前接頭基準尚未指定')
    excluded=source_family('A')|source_family('B');boxes=[];names=[]
    for obj in scene_external_meshes():
        if int(rt.getHandleByAnim(obj)) in excluded:continue
        bb=rt.nodeGetBoundingBox(obj,rt.Matrix3(1));lo,hi=mm(bb[0]),mm(bb[1])
        if max(hi[i]-lo[i] for i in range(3))<1e-6:continue
        boxes.append((lo,hi));names.append(str(obj.name))
    if not boxes:raise ValueError('完整場景中沒有可用的障礙網格')
    a=node('CR_Port_A');b=node('CR_Port_B');pa,pb=mm(a.transform.row4),mm(b.transform.row4)
    # Envelope bounds are rebuilt per calculation; no synthetic chassis is added.
    lo=tuple(min([x[0][i] for x in boxes]+[pa[i],pb[i]]) for i in range(3))
    hi=tuple(max([x[1][i] for x in boxes]+[pa[i],pb[i]]) for i in range(3))
    return dict(boxes=selected_scene.SpatialBoxes(boxes),bounds=(lo,hi),start=pa,goal=pb,
        start_dir=engine.unit(xyz(a.transform.row1)),goal_out=engine.unit(xyz(b.transform.row1))),names

def add_scene_selection_ui(panel,layout):
    group=CollapsibleSection('實際場景接頭與 PoC 預覽 | v1.3.2');form=QtWidgets.QFormLayout(group.body)
    panel.scene_scope=QtWidgets.QComboBox()
    panel.scene_scope.addItem('僅已標示障礙物（原示範功能）','tagged')
    panel.scene_scope.addItem('完整場景網格包圍盒（含其他線材）','all_scene')
    saved=port_prop('CR_Port_A','CR_scene_scope')
    panel.scene_scope.setCurrentIndex(0 if saved=='tagged' else 1)
    form.addRow('障礙物範圍',panel.scene_scope);panel.exit_axes={}
    for endpoint in ('A','B'):
        row=QtWidgets.QHBoxLayout();axis=QtWidgets.QComboBox()
        for basis,label in [('world','世界'),('local','接頭本地')]:
            for i,key in enumerate('XYZ'):
                for sign in (1,-1):axis.addItem(label+(' +' if sign==1 else ' −')+key,'%s:%d:%d'%(basis,i,sign))
        saved_axis=port_prop('CR_Port_'+endpoint,'CR_exit_axis') or ('world:0:1' if endpoint=='A' else 'world:0:-1')
        axis.setCurrentIndex(axis.findData(saved_axis));panel.exit_axes[endpoint]=axis;row.addWidget(axis)
        bind=QtWidgets.QPushButton('所選接頭設為 '+endpoint);row.addWidget(bind);form.addRow('端點 '+endpoint+' 出線方向',row)
        def use_selected(*_,endpoint=endpoint):
            try:
                roots=selected_roots()
                if len(roots)!=1:raise ValueError('請選取一個接頭組立或其網格；不要選取整機或主板組立')
                bind_scene_connector(panel,endpoint,roots[0]);panel.scene_scope.setCurrentIndex(1)
                panel.status.setText(endpoint+' 已設定：'+str(roots[0].name)+'；出線面為包圍盒推定，請檢查輔助物件。')
            except Exception:panel.status.setText(traceback.format_exc().splitlines()[-1])
        bind.clicked.connect(use_selected)
    pair=QtWidgets.QPushButton('框選接頭：以相距最遠兩端作展示配對')
    def use_pair(*_):
        try:
            roots=selected_roots()
            if len(roots)<2:raise ValueError('請框選至少兩個獨立接頭組立')
            if len(roots)>100:raise ValueError('選取範圍太大；請只選接頭組立')
            centers=[]
            for n in roots:
                bb=connector_bounds(n);centers.append(engine.mul(engine.add(bb[0],bb[1]),.5))
            i,j=max(((i,j) for i in range(len(roots)) for j in range(i+1,len(roots))),key=lambda pair:engine.norm(engine.sub(centers[pair[0]],centers[pair[1]])))
            ensure_scene_helpers()
            # Clear previous bindings before replacing both ends, so A/B swapping works.
            for endpoint in ('A','B'):rt.setUserProp(node('CR_Port_'+endpoint),'CR_source_handle',0)
            bind_scene_connector(panel,'A',roots[i]);bind_scene_connector(panel,'B',roots[j]);panel.scene_scope.setCurrentIndex(1)
            panel.status.setText('已設定兩端；相距最遠只是幾何展示配對，電氣相容性與出線面未確認。')
        except Exception:panel.status.setText(traceback.format_exc().splitlines()[-1])
    pair.clicked.connect(use_pair);form.addRow(pair)
    refresh=QtWidgets.QPushButton('依目前方向更新兩端出線面')
    def refresh_axes(*_):
        try:
            for endpoint in ('A','B'):
                source=source_node(endpoint)
                if source is not None:bind_scene_connector(panel,endpoint,source)
            panel.status.setText('出線面已更新；請檢查 CR_Port_A/B 的 +X 方向。')
        except Exception:panel.status.setText(traceback.format_exc().splitlines()[-1])
    refresh.clicked.connect(refresh_axes);form.addRow(refresh)
    preview_button=QtWidgets.QPushButton('生成平滑截面預覽（尚未驗證淨空）')
    preview_button.clicked.connect(lambda *_:create_selected_preview(panel));form.addRow(preview_button)
    note=QtWidgets.QLabel('完整場景只採可轉成網格的物件包圍盒；組立父層不當作實體障礙。\n所選接頭與子零件排除於障礙物清單；接頭內部配合未檢查。出線面需校正。\n完整場景修改後請按重新規劃；不會自動逐秒掃描大型 CAD。')
    note.setWordWrap(True);form.addRow(note);layout.addWidget(group)
    def scope_change(*_):
        port=rt.getNodeByName('CR_Port_A')
        if port is not None:rt.setUserProp(port,'CR_scene_scope',panel.scene_scope.currentData())
        panel.mark_stale()
    panel.scene_scope.currentIndexChanged.connect(scope_change)

def create_selected_preview(panel):
    if panel.busy:return
    panel.busy=True
    try:
        for endpoint in ('A','B'):
            if port_prop('CR_Port_'+endpoint,'CR_datum_status')=='UNASSIGNED':raise ValueError('請先指定 A、B 接頭')
        a=node('CR_Port_A');b=node('CR_Port_B');definition=section_definition(panel)
        segments,data,metrics=selected_scene.preview(engine,sweep,mm(a.transform.row4),mm(b.transform.row4),
            engine.unit(xyz(a.transform.row1)),engine.unit(xyz(b.transform.row1)),xyz(a.transform.row2),xyz(b.transform.row2),
            definition['contours_mm'],panel.inputs['stub'].value(),panel.inputs['bend'].value())
        generation=max([int(rt.getUserProp(n,'CR_generation') or 0) for n in nodes('preview_mesh')]+[0])+1
        mesh=rt.mesh(name='CR_Preview_Section_G%02d'%generation,vertices=rt.Array(*[p3(p) for p in data['vertices']]),
            faces=rt.Array(*[rt.Point3(x+1,y+1,z+1) for x,y,z in data['faces']]))
        tag(mesh,'preview_mesh');mesh.material=material('CR_Unverified_Preview',(245,175,50));mesh.wirecolor=rt.Color(245,175,50)
        rt.setUserProp(mesh,'CR_generation',generation);rt.setUserProp(mesh,'CR_current',True)
        rt.setUserProp(mesh,'CR_route_status','PREVIEW UNVERIFIED');rt.setUserProp(mesh,'CR_cross_section',json.dumps(definition))
        layer('CR_Unverified_Preview').addNode(mesh)
        read=rt.meshop.getVerts(rt.snapshotAsMesh(mesh),rt.Name('all'))
        if len(read)!=len(data['vertices']):raise ValueError('Preview native vertex count mismatch')
        error=max(engine.norm(engine.sub(mm(p),expected)) for p,expected in zip(read,data['vertices']))
        if error>.001:raise ValueError('Preview native vertex readback mismatch')
        metrics.update(data['metrics']);metrics['native_vertex_error_mm']=error;metrics['native_readback_verified']=True
        for old in nodes('preview_mesh'):
            if old!=mesh:old.isHidden=True;rt.setUserProp(old,'CR_current',False)
        report={'version':'1.3.2','kind':'section_preview','recommended_route':None,'metrics':metrics,'section':definition,
            'endpoints':{k:{'source':port_prop('CR_Port_'+k,'CR_source_name'),'datum':port_prop('CR_Port_'+k,'CR_datum_status')} for k in ('A','B')},
            'not_verified':['Complete-scene clearance','Electrical connector matching','Mechanical outlet datums','Optimal routing','Finished sleeve envelope']}
        (OUT/'selected_section_preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        rt.select(mesh);panel.status.setText('已生成橙色截面預覽；線長 %.2f mm。尚未驗證干涉，不列為建議路徑。'%((metrics['length_lower_mm']+metrics['length_upper_mm'])/2))
    except Exception:log(traceback.format_exc());panel.status.setText('截面預覽失敗：'+traceback.format_exc().splitlines()[-1])
    finally:panel.busy=False;rt.redrawViews()


class CollapsibleSection(QtWidgets.QWidget):
    def __init__(self,title,expanded=False):
        super().__init__()
        outer=QtWidgets.QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.toggle=QtWidgets.QToolButton();self.toggle.setText(title)
        self.toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setCheckable(True);self.toggle.setChecked(expanded)
        self.toggle.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,QtWidgets.QSizePolicy.Policy.Fixed)
        self.body=QtWidgets.QWidget();outer.addWidget(self.toggle);outer.addWidget(self.body)
        self.toggle.toggled.connect(self.set_expanded);self.set_expanded(expanded)
    def set_expanded(self,expanded):
        self.body.setVisible(expanded)
        self.toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)

def port_prop(name,key):
    obj=rt.getNodeByName(name)
    return rt.getUserProp(obj,key) if obj is not None else None

def add_demo_ui(panel,layout):
    group=CollapsibleSection('示範場景（手動載入）');form=QtWidgets.QVBoxLayout(group.body)
    button=QtWidgets.QPushButton('加入示範場景')
    form.addWidget(QtWidgets.QLabel('僅適用空白場景；已有模型時請使用實際場景端點。'))
    form.addWidget(button);layout.addWidget(group)
    def load_demo(*_):
        try:
            if any(not rt.getUserProp(obj,'CR_role') for obj in rt.objects):
                raise ValueError('目前已有模型；請在空白場景中手動載入示範。')
            if rt.getNodeByName('CR_Port_A') is not None:
                raise ValueError('場景已設定端點；請改用新的空白場景載入示範。')
            setup_scene();upgrade_mcio_connectors();overview()
            panel.scene_scope.setCurrentIndex(0)
            restore_panel_state(panel);restore_section_state(panel)
            panel.status.setText('示範已加入；請按重新規劃開始計算。')
        except Exception:panel.status.setText(traceback.format_exc().splitlines()[-1])
    button.clicked.connect(load_demo)


class RoutingPanel(QtWidgets.QDialog):
    def __init__(self):
        super().__init__(qtmax.GetQMaxMainWindow())
        self.setWindowTitle('Cable Routing | v1.3.2 接頭模型庫')
        self.setWindowFlags(self.windowFlags()|QtCore.Qt.WindowType.Tool)
        self.resize(720,620);self.report=None;self.busy=False
        root_layout=QtWidgets.QVBoxLayout(self)
        scroll=QtWidgets.QScrollArea(self);scroll.setWidgetResizable(True)
        content=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(content);scroll.setWidget(content);root_layout.addWidget(scroll)
        intro=QtWidgets.QLabel('場景驅動走線：移動障礙物／接頭後，按「重新規劃」。\n三條線是替代方案，不代表可同時安裝。所有參數以 mm 輸入。')
        intro.setWordWrap(True);layout.addWidget(intro)
        parameters_group=CollapsibleSection('路徑規劃參數');form=QtWidgets.QFormLayout(parameters_group.body);self.inputs={}
        for key,label,value,lo,hi in [('diameter','圓線直徑／截面包絡直徑',6,.5,200),('clearance','表面淨空',5,0,50),('bend','最小彎曲半徑',20,1,150),('grid','搜尋網格',10,5,25),('stub','接頭直線出線長度',20,5,80)]:
            sp=QtWidgets.QDoubleSpinBox();sp.setRange(lo,hi);sp.setValue(value);sp.setSuffix(' mm');sp.setDecimals(1)
            self.inputs[key]=sp;form.addRow(label,sp);sp.valueChanged.connect(self.mark_stale)
        layout.addWidget(parameters_group)
        add_section_ui(self,layout)
        add_scene_selection_ui(self,layout)
        add_connector_ui(self,layout)
        operations_group=CollapsibleSection('規劃與保存',True);row=QtWidgets.QHBoxLayout(operations_group.body);layout.addWidget(operations_group)
        for label,callback in [('重新規劃',self.calculate),('選取物件加入障礙物',self.tag_selected),('總覽',overview),('保存 .max / 數據',self.save)]:
            b=QtWidgets.QPushButton(label);b.clicked.connect(callback);row.addWidget(b)
        results_group=CollapsibleSection('計算結果');results_layout=QtWidgets.QVBoxLayout(results_group.body);layout.addWidget(results_group);self.results_group=results_group
        self.table=QtWidgets.QTableWidget(3,6)
        self.table.setHorizontalHeaderLabels(['方案','線長 mm','淨空下限','半徑下限','幾何判定','線長餘量'])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMaximumHeight(170);results_layout.addWidget(self.table)
        self.status=QtWidgets.QLabel('尚未計算');self.status.setWordWrap(True);layout.addWidget(self.status)
        scope=QtWidgets.QLabel('已檢查：讀回原生曲線、包圍盒避障、半徑界限、端點方向與直線段。\n未檢查：真實線材物理、同時佈線、精確網格碰撞、裝配與製造公差。\n修改曲線控制點後須重新規劃；舊結果保留於隱藏圖層。')
        scope.setWordWrap(True);scope_group=CollapsibleSection('驗證範圍與限制');scope_layout=QtWidgets.QVBoxLayout(scope_group.body);scope_layout.addWidget(scope);layout.addWidget(scope_group)
        add_demo_ui(self,layout);layout.addStretch()
        self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.poll_stale);self.timer.start(5000)
        # Position along the right edge, keeping most of the viewport visible.
        main=qtmax.GetQMaxMainWindow();g=main.geometry();self.move(g.right()-self.width()-30,g.top()+40)
        restore_panel_state(self)
        restore_section_state(self)
        self._update_section()

    def parameters(self):return section_parameters(self)
    def mark_stale(self,*_):
        if self.report and not self.busy:
            self.status.setText('參數／場景已修改：需要重新規劃，先前判定已過期。')
            for row in range(3):
                item=self.table.item(row,4)
                if item:item.setText('STALE');item.setForeground(QtGui.QColor('#ffc65b'))
            for n in nodes('result_label'):
                if not n.isHidden and not str(n.text).startswith('STALE'):
                    n.text='STALE | '+str(n.text);n.wirecolor=rt.Color(255,190,65)
    def poll_stale(self):
        if self.busy or not self.report:return
        try:
            if self.scene_scope.currentData()=='all_scene':
                # Full-scene CAD scanning is explicit. Monitor only cheap inputs here.
                old=self.report['scene_signature'];params=self.report['parameters']
                expected=dict(diameter=params['diameter_mm'],clearance=params['clearance_mm'],bend=params['bend_radius_mm'],grid=params['grid_mm'],stub=params['straight_lead_mm'])
                if self.parameters()!=expected or old['start']!=mm(node('CR_Port_A').transform.row4) or old['goal']!=mm(node('CR_Port_B').transform.row4) or old['start_dir']!=engine.unit(xyz(node('CR_Port_A').transform.row1)) or old['goal_out']!=engine.unit(xyz(node('CR_Port_B').transform.row1)) or cable_metadata(self)!=self.report.get('cable_specification'):self.mark_stale()
                return
            current,_=scene_input()
            params=self.report['parameters']
            expected=dict(diameter=params['diameter_mm'],clearance=params['clearance_mm'],bend=params['bend_radius_mm'],grid=params['grid_mm'],stub=params['straight_lead_mm'])
            if current!=self.report['scene_signature'] or self.parameters()!=expected or route_signature()!=self.report['route_signature'] or cable_metadata(self)!=self.report.get('cable_specification') or sweep_signature()!=self.report.get('sweep_signature'):self.mark_stale()
        except Exception:self.mark_stale()
    def calculate(self,*_):
        if self.busy:return
        self.busy=True;self.report=None;self.table.clearContents();self.status.setText('計算與驗證中…');QtWidgets.QApplication.processEvents()
        try:
            self.report=replan(self.parameters());attach_section_meshes(self);attach_cable_metadata(self);self.fill_table()
            best=self.report['recommended_route']
            self.status.setText(('包圍盒幾何建議方案 %s；'%best if best else '未找到通過包圍盒條件的方案；不能据此判定真實模型無路徑；')+' %.2f 秒。結果來自目前場景。'%self.report['elapsed_seconds'])
        except Exception:
            log(traceback.format_exc());self.status.setText('重算失敗：'+traceback.format_exc().splitlines()[-1]+'；先前結果已過期。')
        finally:self.busy=False;rt.redrawViews()
    def fill_table(self):
        self.results_group.toggle.setChecked(True)
        for row,r in enumerate(self.report['routes']):
            m=r['metrics'];values=[str(r['route'])]+['%.2f'%m[k] if m.get(k) is not None else '—' for k in ('length_mm','clearance_lower_mm','radius_lower_mm')]+[m['status'],('%.1f'%r['nominal_length_margin_mm']) if r.get('nominal_length_margin_mm') is not None else '未指定']
            for col,v in enumerate(values):
                item=QtWidgets.QTableWidgetItem(v);item.setForeground(QtGui.QColor('#9ee68b' if m['accepted'] else '#ff7a7a'));self.table.setItem(row,col,item)
    def tag_selected(self,*_):
        count=0
        for obj in list(rt.selection):
            if rt.getUserProp(obj,'CR_role') in ('port','connector','connector_model','route_mesh','preview_mesh','bounds','route','fixture','label','result_label','camera'):continue
            tag(obj,'obstacle');count+=1
        self.status.setText('已加入 %d 個障礙物；請重新規劃。'%count)
    def save(self,*_):
        try:
            current,_=scene_input()
            if not self.report or current!=self.report['scene_signature']:
                self.status.setText('請先重新規劃，再保存計算結果。');return
            self.calculate()
            if not self.report:return
            if self.report['scene_signature']!=scene_input()[0]:return
            save_scene();write_report(self.report);capture();self.status.setText('已保存至：'+str(OUT))
        except Exception:log(traceback.format_exc());self.status.setText('保存失敗；詳見 max_execution_log.txt。')

def main():
    old=getattr(sys,'_cr_max_panel',None)
    if old is not None:old.timer.stop();old.close()
    panel=RoutingPanel();sys._cr_max_panel=panel;panel.show()
    panel.status.setText('請設定 A、B 接頭後手動規劃。開啟工具不會加入模型或計算路徑。')


try:main()
except Exception:
    log(traceback.format_exc())
    rt.messageBox('Cable Routing 原型遇到錯誤。詳見 outputs/max_execution_log.txt。',title='Cable Routing')
