"""虚拟校园：多边形形状是唯一来源，栅格由这些形状保守生成。"""
import json
from pathlib import Path
W,H=420,280
shapes=[
 {'kind':'building','label':'快递中心','points':[[9,9],[31,9],[34,15],[30,25],[10,24],[7,17]]},
 {'kind':'building','label':'图书馆','points':[[43,8],[62,6],[70,13],[66,25],[47,24],[40,18]]},
 {'kind':'building','label':'教学楼','points':[[79,8],[102,10],[108,19],[102,27],[81,24],[76,18]]},
 {'kind':'building','label':'实验楼','points':[[10,49],[26,46],[33,52],[30,65],[21,69],[9,64],[6,56]]},
 {'kind':'building','label':'活动中心','points':[[47,47],[64,45],[72,51],[69,65],[57,70],[44,63]]},
 {'kind':'building','label':'宿舍 A','points':[[87,47],[107,45],[113,53],[110,66],[91,69],[83,60]]},
 {'kind':'water','label':'景观池','points':[[34,31],[39,28],[44,29],[47,33],[45,37],[40,39],[35,37],[32,34]]},
 {'kind':'green','label':'花园','points':[[74,31],[79,29],[84,30],[88,34],[86,38],[81,40],[76,39],[72,35]]},
 {'kind':'stairs','label':'台阶','points':[[19,26],[27,26],[28,29],[20,29]]},
 {'kind':'stairs','label':'台阶','points':[[91,42],[100,42],[100,45],[91,45]]},
]
landmarks=[{'name':'快递取件点','x':16,'y':34},{'name':'宿舍取件点','x':100,'y':39},{'name':'校园广场','x':61,'y':36}]

# The original campus remains in the northwest. New sectors contain physical
# flowerbed walls, a one-way corridor, a two-way corridor and a diagonal passage.
shapes.extend([
 {'kind':'building','label':'东区教学楼','points':[[195,14],[230,14],[230,42],[195,42]]},
 {'kind':'building','label':'研究中心','points':[[250,20],[282,20],[287,46],[252,49]]},
 {'kind':'building','label':'南区宿舍','points':[[102,144],[136,140],[144,172],[108,180]]},
 {'kind':'building','label':'配送仓库','points':[[158,169],[185,169],[185,191],[158,191]]},
 {'kind':'green','label':'东区花坛','points':[[199,67],[226,60],[241,77],[222,92],[198,85]]},
 {'kind':'green','label':'南区花坛','points':[[26,146],[70,146],[76,178],[27,180]]},
 {'kind':'water','label':'西侧景观河','points':[[212,110],[225,110],[225,186],[212,186]]},
 {'kind':'water','label':'东侧景观河','points':[[235,110],[248,110],[248,186],[235,186]]},
 {'kind':'building','label':'体育馆','points':[[130,9],[163,9],[168,18],[163,32],[130,30]]},
 {'kind':'building','label':'创新中心','points':[[131,45],[161,45],[165,62],[151,69],[130,62]]},
 {'kind':'green','label':'东区花坛','points':[[115,16],[120,13],[124,18],[122,25],[116,24]]},
 {'kind':'green','label':'环岛花坛','points':[[113,47],[119,44],[124,49],[120,54],[114,53]]},
 {'kind':'green','label':'南区花坛','points':[[12,78],[76,78],[76,84],[12,84]]},
 {'kind':'green','label':'隔离花坛','points':[[12,96],[76,96],[76,102],[12,102]]},
 {'kind':'green','label':'南侧花坛','points':[[12,114],[76,114],[76,117],[12,117]]},
 {'kind':'green','label':'窄道北壁','points':[[39,103],[40,103],[40,105],[39,105]]},
 {'kind':'green','label':'避让位北壁','points':[[41,103],[45,103],[45,104],[41,104]]},
 {'kind':'green','label':'窄道北壁','points':[[46,103],[47,103],[47,105],[46,105]]},
 {'kind':'green','label':'窄道南壁','points':[[39,110],[47,110],[47,113],[39,113]]},
 {'kind':'green','label':'斜道北侧花坛','points':[[100,73],[164,105],[164,109],[100,77]]},
 {'kind':'green','label':'斜道南侧花坛','points':[[97,85],[161,117],[153,117],[97,89]]},
])

# East and south districts extend the campus without changing old coordinates.
shapes.extend([
 {'kind':'building','label':'东区宿舍 B','points':[[316,12],[347,12],[350,39],[315,39]]},
 {'kind':'building','label':'信息工程楼','points':[[365,12],[401,12],[403,42],[366,42]]},
 {'kind':'building','label':'东区体育馆','points':[[327,84],[376,84],[380,111],[330,116]]},
 {'kind':'building','label':'医学实验楼','points':[[315,128],[350,128],[355,159],[316,159]]},
 {'kind':'building','label':'东门服务站','points':[[367,161],[400,161],[401,184],[368,184]]},
 {'kind':'building','label':'南区教学楼','points':[[29,199],[68,199],[70,218],[30,218]]},
 {'kind':'building','label':'南区图书馆','points':[[124,197],[160,197],[164,218],[125,218]]},
 {'kind':'building','label':'南区宿舍 B','points':[[204,199],[237,199],[240,219],[207,219]]},
 {'kind':'building','label':'能源中心','points':[[302,199],[338,199],[340,218],[303,218]]},
 {'kind':'building','label':'东南研发中心','points':[[365,199],[402,199],[404,218],[367,218]]},
 {'kind':'green','label':'东区中央花园','points':[[309,54],[336,54],[341,70],[315,70]]},
 {'kind':'green','label':'南区生态花园','points':[[75,200],[110,200],[110,217],[75,217]]},
 {'kind':'water','label':'东区水景','points':[[355,122],[369,122],[369,148],[355,148]]},
])

# Road centre lines are the shared source for routing cells and both map views.
# Cross streets and two north-south routes form loops; building aprons join
# entrances to those streets instead of leaving open ground fully traversable.
roads = [
 {'label':'北环路','points':[[15,36],[288,36]],'width':12},
 {'label':'中环路','points':[[15,72],[288,72]],'width':10},
 {'label':'南环路','points':[[15,148],[288,148]],'width':10},
 {'label':'南门路','points':[[15,185],[288,185]],'width':10},
 {'label':'西纵路','points':[[20,35],[20,185]],'width':9},
 {'label':'西北避池路','points':[[16,44],[39,44]],'width':7},
 {'label':'实验楼西侧路','points':[[39,44],[39,72]],'width':7},
 {'label':'图书馆路','points':[[60,30],[60,185]],'width':9},
 {'label':'北区东联络路','points':[[127,36],[127,72]],'width':9},
 {'label':'宿舍路','points':[[100,36],[100,185]],'width':9},
 {'label':'中央纵路','points':[[180,36],[180,194]],'width':10},
 {'label':'桥头路','points':[[190,36],[190,194]],'width':9},
 {'label':'河心路','points':[[230,36],[230,185]],'width':9},
 {'label':'东纵路','points':[[270,52],[270,185]],'width':10},
 {'label':'单向通道','points':[[13,90],[76,90]],'width':11},
 {'label':'单向通道东出口','points':[[76,90],[100,90]],'width':7},
 {'label':'双向通道','points':[[13,108],[76,108]],'width':11},
 {'label':'通道东绕行路','points':[[82,72],[82,114]],'width':9},
 {'label':'通道西绕行路','points':[[8,72],[8,114]],'width':9},
 {'label':'通道西入口','points':[[8,90],[20,90]],'width':7},
 {'label':'通道西出口','points':[[8,108],[20,108]],'width':7},
 {'label':'中部横路','points':[[20,108],[205,108]],'width':10},
 {'label':'东部横路','points':[[230,108],[280,108]],'width':10},
 {'label':'斜向通道','points':[[100,82],[160,112]],'width':10},
 {'label':'东南联络路','points':[[190,148],[270,148]],'width':10},
]
roads.extend([
 {'label':'北环路东延','points':[[280,36],[408,36]],'width':12},
 {'label':'中环路东延','points':[[280,72],[408,72]],'width':10},
 {'label':'中部横路东延','points':[[280,108],[408,108]],'width':10},
 {'label':'南环路东延','points':[[280,148],[408,148]],'width':10},
 {'label':'南门路东延','points':[[280,185],[408,185]],'width':10},
 {'label':'东环纵路','points':[[330,36],[330,260]],'width':10},
 {'label':'东门纵路','points':[[385,36],[385,260]],'width':10},
 {'label':'南区第一横路','points':[[20,230],[408,230]],'width':10},
 {'label':'南区环路','points':[[20,262],[408,262]],'width':10},
 {'label':'南区西纵路','points':[[20,180],[20,262]],'width':9},
 {'label':'南区图书馆路','points':[[145,185],[145,262]],'width':9},
 {'label':'南区宿舍路','points':[[225,185],[225,262]],'width':9},
 {'label':'南区中央纵路','points':[[180,185],[180,262]],'width':9},
 {'label':'南区东纵路','points':[[270,185],[270,262]],'width':9},
 {'label':'南区西联络路','points':[[60,185],[60,262]],'width':9},
 {'label':'南区中联络路','points':[[100,185],[100,262]],'width':9},
 {'label':'东区斜向路','points':[[285,80],[320,109]],'width':8},
])
for shape in shapes:
 if shape['kind'] != 'building': continue
 xs = [p[0] for p in shape['points']]; ys = [p[1] for p in shape['points']]
 center = (min(xs)+max(xs))//2; apron_y = min(H-4,max(ys)+4)
 roads.append({'label':shape['label']+'入口路','points':[[min(xs)-3,apron_y],[max(xs)+3,apron_y]],'width':7})
 nearest = min((36,72,108,148,185,230,262),key=lambda y:abs(y-apron_y))
 roads.append({'label':shape['label']+'接驳路','points':[[center,apron_y],[center,nearest]],'width':7})

def near_road(x,y,road):
 (ax,ay),(bx,by)=road['points']; dx=bx-ax;dy=by-ay
 length_sq=dx*dx+dy*dy
 t=max(0,min(1,((x+.5-ax)*dx+(y+.5-ay)*dy)/length_sq)) if length_sq else 0
 return ((x+.5-ax-t*dx)**2+(y+.5-ay-t*dy)**2)**.5 <= road['width']/2

def inside(p,poly):
 x,y=p; result=False
 for i,(ax,ay) in enumerate(poly):
  bx,by=poly[(i+1)%len(poly)]
  if (ay>y)!=(by>y) and x < (bx-ax)*(y-ay)/(by-ay)+ax: result=not result
 return result

def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def intersect(a,b,c,d):
 def on(a,b,p): return min(a[0],b[0])<=p[0]<=max(a[0],b[0]) and min(a[1],b[1])<=p[1]<=max(a[1],b[1])
 ab1,ab2=orient(a,b,c),orient(a,b,d);cd1,cd2=orient(c,d,a),orient(c,d,b)
 if ab1==0 and on(a,b,c) or ab2==0 and on(a,b,d) or cd1==0 and on(c,d,a) or cd2==0 and on(c,d,b): return True
 return (ab1>0)!=(ab2>0) and (cd1>0)!=(cd2>0)
def overlaps(x,y,poly):
 box=[(x,y),(x+1,y),(x+1,y+1),(x,y+1)]
 if any(inside(p,poly) for p in box): return True
 if any(x<=px<=x+1 and y<=py<=y+1 for px,py in poly): return True
 return any(intersect(box[i],box[(i+1)%4],poly[j],poly[(j+1)%len(poly)]) for i in range(4) for j in range(len(poly)))

def generate():
 cells=[['green']*W for _ in range(H)]
 for road in roads:
  (ax,ay),(bx,by)=road['points']; pad=road['width']/2+1
  for y in range(max(0,int(min(ay,by)-pad)),min(H,int(max(ay,by)+pad+1))):
   for x in range(max(0,int(min(ax,bx)-pad)),min(W,int(max(ax,bx)+pad+1))):
    if near_road(x,y,road): cells[y][x]='road'
 for shape in shapes:
  poly=shape['points']; xs=[p[0] for p in poly];ys=[p[1] for p in poly]
  for y in range(max(0,min(ys)-1),min(H,max(ys)+1)):
   for x in range(max(0,min(xs)-1),min(W,max(xs)+1)):
    if overlaps(x,y,poly): cells[y][x]=shape['kind']
 lanes=[
  {'label':'单向通道 →','direction':[1,0],'cells':[[x,y] for y in range(85,96) for x in range(13,76) if cells[y][x]=='road'],'label_position':[44,90]},
  {'label':'双向通道 ↔','direction':None,'cells':[[x,y] for y in range(103,114) for x in range(13,76) if cells[y][x]=='road'],'label_position':[44,108]},
  {'label':'斜向通道','direction':None,'cells':[[x,y] for x in range(100,161) for y in range(78,117) if cells[y][x]=='road' and 2<=y-(x-100)*.5-77<=7],'label_position':[130,97]},
 ]
 agents=[{'start':[16,34],'goal':[100,39]},{'start':[100,39],'goal':[16,34]},
         {'start':[54,36],'goal':[66,36]},{'start':[60,30],'goal':[60,42]}]
 scenarios=[{'name':'校园交会 · 四机器人','agents':agents},
            {'name':'立体校园 · 五机器人','agents':[{'start':[190,148,1],'goal':[270,148,1]}, {'start':[230,130,0],'goal':[230,170,0]}, {'start':[270,150,1],'goal':[190,150,1]}, {'start':[190,149,1],'goal':[230,149,6]}, {'start':[230,175,0],'goal':[230,125,0]}]},
            {'name':'桥上桥下 · 同时交会','agents':[{'start':[220,148,6],'goal':[240,148,6]}, {'start':[230,138,0],'goal':[230,158,0]}]},
            {'name':'坡道汇入 · 双车协同','agents':[{'start':[182,148,0],'goal':[218,148,6]}, {'start':[190,150,1],'goal':[218,150,6]}]},
            {'name':'校园协同 · 五机器人','agents':agents+[{'start':[116,35],'goal':[153,36]}]},
            {'name':'窄道调速 · 五机器人','agents':[{'start':[18,108],'goal':[70,108]},{'start':[70,108],'goal':[18,108]}, {'start':[16,34],'goal':[20,34]},{'start':[54,36],'goal':[57,36]},{'start':[140,37],'goal':[153,37]}]},
            {'name':'单向通道 · 逆向绕行','agents':[{'start':[18,90],'goal':[70,90]},{'start':[70,92],'goal':[18,92]}]},
            {'name':'双向通道 · 对向通过','agents':[{'start':[18,108],'goal':[70,108]},{'start':[70,108],'goal':[18,108]}]},
            {'name':'斜向通道 · 对向通过','agents':[{'start':[104,83],'goal':[156,109]},{'start':[156,109],'goal':[104,83]}]},
            {'name':'路口交会 · 错时通过','agents':[{'start':[54,36],'goal':[66,36]},{'start':[60,30],'goal':[60,42]}]}]
 bridge={'start':186,'end':274,'plateau_start':210,'plateau_end':250,'height':6,'y_min':145,'y_max':151,'thickness':.5}
 return {'name':'虚拟校园 · 星河校区','width':W,'height':H,'resolution_m':1,'shapes':shapes,'roads':roads,'cells':cells,'landmarks':landmarks,'lanes':lanes,'bridge':bridge,'scenarios':scenarios,'default_agents':agents,'default_start':[16,34],'default_goal':[100,39],'note':'虚构校园，坐标与尺寸仅用于演示。'}
if __name__=='__main__':
 Path(__file__).with_name('campus_map.json').write_text(json.dumps(generate(),ensure_ascii=False,separators=(',',':')),encoding='utf-8');print('已生成 campus_map.json')
