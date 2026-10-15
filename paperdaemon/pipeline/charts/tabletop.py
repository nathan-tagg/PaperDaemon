r"""Tabletop house specs -> Vega-Lite. No code, network, or game rules in input.

The existing chart renderer remains the public entry point. Layout errors are
explicit; content is never silently cropped, summarized, or shrunk to fit.
"""
from __future__ import annotations
import copy
import json
import math
from collections import defaultdict
from copy import deepcopy

# ==================================================================================================
# Single source of truth for the model-facing, data-only tabletop contract.
# ==================================================================================================

TYPES = ('game_board', 'player_mat', 'card_deck', 'character_sheet',
         'gm_screen', 'encounter_tracker', 'adventure', 'token_sheet', 'dialog')
# a character's face comes in these (rm_faces draws them; games/characters holds who is who). The
# same eighteen as rm_faces.EMOTIONS: a feeling missing here would fail validation and cost the strip its faces
EMOTIONS = ('neutral', 'happy', 'sad', 'angry', 'jealous', 'worried', 'relieved', 'thinking',
            'surprised', 'smug', 'determined', 'confused', 'curious', 'hopeful', 'embarrassed',
            'disappointed', 'skeptical', 'tired')
# the subtle frames a face can carry over its emotion (rm_faces.MARKS): a tell, never an emotion
MARKS = ('glint', 'bead', 'twitch', 'brow_up', 'knit', 'narrow', 'glance', 'blink', 'flush', 'pale',
         'press', 'smirk', 'jaw', 'nostrils', 'ear_flick', 'glitch', 'led', 'static', 'twinkle')
# ...and the marks a character pack's faces can show (rm_cast.MARKS: signature and tell slots, and any
# the pack adds), the same list rm_characters accepts. Left out, a turn whose face showed a signature
# failed the whole dialog, and the game page lost the opponent's face and name.
try:
    from paperdaemon.pipeline.games import cast as _cast
    MARKS = tuple(dict.fromkeys(MARKS + tuple(_cast.MARKS)))
except Exception:                       # without the pipeline beside it: the faces' own marks
    pass
COLORS = ['blue','teal','green','yellow','orange','red','magenta','plum','gray','white',
          'sage','clay','sand','rose','slate','cyan','pink','lime','purple','ice','pale']
PAGES = ['tablet','tablet-wide','half','third','strip','wide','square']
def text(n=180, minimum=0): return {'type':'string','maxLength':n,'minLength':minimum}
def integer(lo,hi): return {'type':'integer','minimum':lo,'maximum':hi}
def arr(item,lo=0,hi=24): return {'type':'array','items':item,'minItems':lo,'maxItems':hi}
def obj(props,required=()):
    return {'type':'object','properties':props,'required':list(required),'additionalProperties':False}
ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]{0,47}$'}
COLOR={'enum':COLORS}
BOOL={'type':'boolean'}
VALUE={'anyOf':[text(80),{'type':'number','minimum':-1000000,'maximum':1000000}]}
FIELD=obj({'label':text(36,1),'value':VALUE},['label'])
RESOURCE=obj({'id':ID,'label':text(26,1),'value':integer(0,100),'max':integer(1,100),'color':COLOR},['label','max'])
SECTION=obj({'title':text(48,1),'text':text(1500),'items':arr(text(160),0,20),
             'columns':arr(text(36,1),1,5),'rows':arr(arr(VALUE,1,5),0,20),'lines':integer(0,12),
             'color':COLOR},['title'])
CELL=obj({'row':integer(0,23),'col':integer(0,23),'label':text(16),'color':COLOR,
          'icon':text(40)},['row','col'])
PIECE=obj({'row':integer(0,23),'col':integer(0,23),'label':text(6,1),
           'side':{'enum':['light','dark']},'color':COLOR},['row','col','label'])
CARD=obj({'id':ID,'title':text(54,1),'subtitle':text(60),'body':text(650),
          'kind':text(32),'icon':text(40),'color':COLOR,'cost':text(48),
          'stats':arr(FIELD,0,4),'footer':text(95)},['title','body'])
SLOT=obj({'title':text(40,1),'text':text(120),'icon':text(40),'color':COLOR},['title'])
LANE=obj({'title':text(28,1),'action':text(100),'color':COLOR,
          'slots':arr(SLOT,0,5)},['title'])
ACTOR=obj({'name':text(36,1),'initiative':integer(-99,99),'hp':text(18),
           'defense':text(12),'conditions':arr(text(24,1),0,4),'notes':text(100)},['name'])
TOKEN=obj({'label':text(12,1),'subtitle':text(28),'icon':text(40),
           'color':COLOR,'count':integer(1,24)},['label'])
CONDITION=obj({'items':arr(ID,0,16),'flags':arr(ID,0,16),'not_flags':arr(ID,0,16),
               'resources':{'type':'object','additionalProperties':integer(0,100),'maxProperties':12}})
EFFECT=obj({'give':arr(ID,0,12),'take':arr(ID,0,12),'set_flags':arr(ID,0,12),
            'clear_flags':arr(ID,0,12),
            'resources':{'type':'object','additionalProperties':integer(-100,100),'maxProperties':12}})
CHOICE=obj({'id':ID,'label':text(90,1),'to':ID,'aliases':arr(text(40,1),0,6),
            'requires':CONDITION,'effects':EFFECT},['id','label','to'])
SCENE=obj({'id':ID,'title':text(60,1),'text':text(1600,1),'choices':arr(CHOICE,0,6),
           'ending':BOOL,'icon':text(40),'color':COLOR},['id','title','text','choices'])
STATE=obj({'scene':ID,'inventory':arr(ID,0,32),'flags':arr(ID,0,32),
           'resources':{'type':'object','additionalProperties':integer(0,100),'maxProperties':12},
           'turn':integer(0,100000)},['scene','inventory','flags','resources','turn'])
# DIALOG: who says what, in order. A speaker line is a face and a speech bubble; the same line
# with no text is an emote (a face alone); a narrator line is the game master's words, no face.
SPEAKER=obj({'speaker':ID,'emotion':{'enum':list(EMOTIONS)},'text':text(360,1),
             'marks':{'type':'array','items':{'enum':list(MARKS)},'maxItems':3,'uniqueItems':True},
             'front':ID},['speaker','emotion'])     # front: whose face, for a character with alters
NARRATOR=obj({'narrator':text(360,1)},['narrator'])
COMMON={'type':{},'version':{'const':1},'title':text(90,1),'subtitle':text(160),
        'page':{'enum':PAGES},'width':integer(600,2400),'height':integer(500,3200),
        'accent':COLOR,'footer':text(180)}
PROPS={
 'game_board':({'grid':{'enum':['square','hex']},'rows':integer(2,24),'cols':integer(2,24),
                'checkered':BOOL,'coordinates':BOOL,'cells':arr(CELL,0,576),
                'pieces':arr(PIECE,0,64),'notes':arr(text(130),0,4)},['rows','cols']),
 'player_mat':({'lanes':arr(LANE,1,5),'slots_per_lane':integer(1,5),
                'resources':arr(RESOURCE,0,6),'notes':arr(text(150),0,5)},['lanes']),
 'card_deck':({'cards':arr(CARD,1,120),'columns':integer(1,4),'rows':integer(1,5),
               'sheet':integer(1,120),'cut_guides':BOOL},['cards']),
 'character_sheet':({'identity':arr(FIELD,1,8),'stats':arr(FIELD,0,8),
                     'resources':arr(RESOURCE,0,6),'sections':arr(SECTION,1,8)},['identity','sections']),
 'gm_screen':({'panels':arr(obj({'title':text(36,1),'sections':arr(SECTION,1,5)},['title','sections']),1,4)},['panels']),
 'encounter_tracker':({'round':integer(1,100),'rounds':integer(1,30),'actors':arr(ACTOR,1,12),
                       'resources':arr(RESOURCE,0,4),'notes':arr(text(160),0,6)},['actors']),
 'token_sheet':({'tokens':arr(TOKEN,1,48),'columns':integer(2,8),'shape':{'enum':['circle','square']}},['tokens']),
 'adventure':({'start':ID,'scenes':arr(SCENE,1,80),'items':arr(obj({'id':ID,'label':text(40,1)},['id','label']),0,32),
               'flags':arr(ID,0,32),'resources':arr(obj({'id':ID,'label':text(26,1),'value':integer(0,100),
                       'max':integer(1,100),'color':COLOR},['id','label','value','max']),0,12),
               'initial_inventory':arr(ID,0,32),'initial_flags':arr(ID,0,32),'state':STATE},['start','scenes']),
 'dialog':({'lines':arr({'oneOf':[SPEAKER,NARRATOR]},1,8)},['lines']),
}
# a dialog strip needs no title; every other tabletop sheet has one
UNTITLED=('dialog',)
SCHEMAS={k:obj(dict(COMMON, type={'const':k}, **v[0]),['type',*(() if k in UNTITLED else ('title',)),*v[1]])
         for k,v in PROPS.items()}
SCHEMA={'$schema':'https://json-schema.org/draft/2020-12/schema',
        '$id':'urn:remarkable:tabletop:v1','title':'reMarkable tabletop house spec v1',
        'oneOf':[deepcopy(SCHEMAS[t]) for t in TYPES]}


PRESETS={
 'game_board':('square',576), 'player_mat':('tablet-wide',5),
 'card_deck':('tablet',120), 'character_sheet':('tablet',8),
 'gm_screen':('tablet-wide',4), 'encounter_tracker':('tablet',12),
 'adventure':('tablet',80), 'token_sheet':('tablet',96), 'dialog':('strip',8)}

def fail(path,message):
    from paperdaemon.pipeline.charts import SpecError
    raise SpecError(f'{path}: {message}')

def unique(values,path):
    if len(values)!=len(set(values)): fail(path,'duplicates are not allowed')

def validate(spec):
    import jsonschema
    from paperdaemon.pipeline import charts as CH
    try:
        raw=json.dumps(spec,allow_nan=False,ensure_ascii=False)
    except (ValueError,TypeError,RecursionError) as e:
        fail('$','must be finite, acyclic JSON data: '+str(e))
    if len(raw.encode('utf-8'))>524288: fail('$','spec exceeds 512 KiB')
    if not isinstance(spec,dict) or spec.get('type') not in TYPES: fail('type','unknown tabletop type')
    checker=jsonschema.Draft202012Validator.TYPE_CHECKER.redefine('integer',lambda checker,value:type(value) is int)
    validator=jsonschema.validators.extend(jsonschema.Draft202012Validator,type_checker=checker)
    errors=list(validator(SCHEMAS[spec['type']]).iter_errors(spec))
    if errors:
        e=min(errors,key=lambda e:(len(e.absolute_path),str(e.absolute_path)))
        path='$'+''.join(f'[{i}]' if isinstance(i,int) else '.'+i for i in e.absolute_path)
        fail(path,e.message)
    def walk(v,path='$'):
        if isinstance(v,dict):
            if 'icon' in v and v['icon'] not in CH.ICONS and v['icon'] not in CH.ALIASES:
                fail(path+'.icon','unknown icon; use rm_chart.ICONS or omit it')
            if 'max' in v and v.get('value',0)>v['max']: fail(path+'.value','exceeds max')
            if 'rows' in v and 'columns' in v and isinstance(v['columns'],list):
                for i,row in enumerate(v['rows']):
                    if len(row)!=len(v['columns']): fail(path+f'.rows[{i}]','cell count must match columns')
            for k,x in v.items(): walk(x,path+'.'+k)
        elif isinstance(v,list):
            for i,x in enumerate(v): walk(x,path+f'[{i}]')
    walk(spec)
    t=spec['type']
    if t=='game_board':
        for key in ('cells','pieces'):
            vals=spec.get(key,[]);unique([(v['row'],v['col']) for v in vals],key)
            for i,v in enumerate(vals):
                if v['row']>=spec['rows'] or v['col']>=spec['cols']: fail(f'{key}[{i}]','outside board')
    elif t=='player_mat':
        for i,lane in enumerate(spec['lanes']):
            if len(lane.get('slots',[]))>spec.get('slots_per_lane',4): fail(f'lanes[{i}].slots','more slots than slots_per_lane')
    elif t=='card_deck':
        ids=[c['id'] for c in spec['cards'] if 'id' in c];unique(ids,'cards.id')
        pages=math.ceil(len(spec['cards'])/(spec.get('columns',2)*spec.get('rows',3)))
        if spec.get('sheet',1)>pages: fail('sheet',f'only {pages} sheet(s) exist')
    elif t=='token_sheet':
        if sum(x.get('count',1) for x in spec['tokens'])>96: fail('tokens','at most 96 tokens per sheet')
    elif t=='adventure':
        _validate_adventure(spec)
    elif t=='dialog':
        from paperdaemon.pipeline.games import characters as RC
        known=RC.roster()
        for i,ln in enumerate(spec['lines']):
            if 'speaker' in ln and ln['speaker'] not in known:
                fail(f'lines[{i}].speaker',f"no character {ln['speaker']!r}; the roster has "+', '.join(sorted(known)))
            if ln.get('front') and ln['front'] not in RC.alters(ln['speaker']):
                fail(f'lines[{i}].front',f"{ln['speaker']} has no alter {ln['front']!r}")
    return spec

def _validate_adventure(s):
    scenes={x['id']:x for x in s['scenes']};unique([x['id'] for x in s['scenes']],'scenes.id')
    items={x['id'] for x in s.get('items',[])};unique([x['id'] for x in s.get('items',[])],'items.id')
    flags=set(s.get('flags',[]));unique(s.get('flags',[]),'flags')
    resources={x['id']:x for x in s.get('resources',[])};unique([x['id'] for x in s.get('resources',[])],'resources.id')
    if s['start'] not in scenes: fail('start','unknown scene')
    def refs(values,known,path):
        unique(values,path)
        for v in values:
            if v not in known: fail(path,f'unknown identifier {v!r}')
    refs(s.get('initial_inventory',[]),items,'initial_inventory')
    refs(s.get('initial_flags',[]),flags,'initial_flags')
    for i,node in enumerate(s['scenes']):
        p=f'scenes[{i}]';commands=[]
        if bool(node.get('ending',False)) != (not node['choices']): fail(p,'a scene with no choices must be an ending; endings cannot have choices')
        for j,c in enumerate(node['choices']):
            cp=f'{p}.choices[{j}]'
            if c['to'] not in scenes: fail(cp+'.to','unknown scene')
            for cmd in [c['id'],*c.get('aliases',[])]:
                normalized=cmd.strip().lower()
                if not normalized or normalized in ('look','help','inventory','restart') or normalized.isdecimal(): fail(cp,'empty/reserved command or numeric alias')
                commands.append(normalized)
            r=c.get('requires',{});e=c.get('effects',{})
            for k in ('items',): refs(r.get(k,[]),items,cp+'.requires.'+k)
            for k in ('flags','not_flags'): refs(r.get(k,[]),flags,cp+'.requires.'+k)
            if set(r.get('flags',[]))&set(r.get('not_flags',[])): fail(cp,'contradictory flag requirements')
            for k in ('give','take'): refs(e.get(k,[]),items,cp+'.effects.'+k)
            for k in ('set_flags','clear_flags'): refs(e.get(k,[]),flags,cp+'.effects.'+k)
            if set(e.get('give',[]))&set(e.get('take',[])): fail(cp,'cannot give and take the same item')
            if set(e.get('set_flags',[]))&set(e.get('clear_flags',[])): fail(cp,'cannot set and clear the same flag')
            for container in (r,e):
                refs(list(container.get('resources',{})),resources,cp+'.resources')
            for k,v in r.get('resources',{}).items():
                if v>resources[k]['max']: fail(cp+'.requires.resources','requirement exceeds declared maximum')
        unique(commands,p+'.commands')
    reached=set();todo=[s['start']]
    while todo:
        n=todo.pop()
        if n in reached: continue
        reached.add(n);todo.extend(c['to'] for c in scenes[n]['choices'])
    if reached!=set(scenes): fail('scenes','unreachable scenes: '+', '.join(sorted(set(scenes)-reached)))
    if not any(x.get('ending') for x in s['scenes']): fail('scenes','include at least one ending')
    if 'state' in s:
        st=s['state']
        if st['scene'] not in scenes: fail('state.scene','unknown scene')
        refs(st['inventory'],items,'state.inventory');refs(st['flags'],flags,'state.flags')
        if set(st['resources'])!=set(resources): fail('state.resources','must match declared resources exactly')
        for k,v in st['resources'].items():
            if v>resources[k]['max']: fail('state.resources.'+k,'exceeds maximum')

def advise(t):
    from paperdaemon.pipeline import charts as CH
    page,cap=PRESETS[t];w,h=CH.PAGES[page]
    return dict(type=t,aspect=h/w,page=page,share=1.0,cap=cap,suggested=(w,h),
                data_only=True,version=1,notes='Do not shrink dense content. Use more sheets or shorter text.')

def initial_state(spec):
    validate(spec)
    if spec['type']!='adventure': fail('type','initial_state requires adventure')
    return dict(scene=spec['start'],inventory=list(spec.get('initial_inventory',[])),
                flags=list(spec.get('initial_flags',[])),resources={x['id']:x['value'] for x in spec.get('resources',[])},turn=0)

def _available(c,st):
    r=c.get('requires',{});e=c.get('effects',{})
    return (set(r.get('items',[]))<=set(st['inventory']) and
            set(r.get('flags',[]))<=set(st['flags']) and
            not set(r.get('not_flags',[]))&set(st['flags']) and
            all(st['resources'].get(k,0)>=v for k,v in r.get('resources',{}).items()) and
            set(e.get('take',[]))<=set(st['inventory']) and
            all(st['resources'].get(k,0)+v>=0 for k,v in e.get('resources',{}).items()))

def adventure_view(spec,state=None):
    state=copy.deepcopy(state if state is not None else spec.get('state',initial_state(spec)))
    validate(dict(spec,state=state))
    node=next(n for n in spec['scenes'] if n['id']==state['scene'])
    return dict(scene=copy.deepcopy(node),state=state,
                choices=[dict(c,available=_available(c,state)) for c in node['choices']])

def advance(spec,state,command):
    """Atomic deterministic transition. Returns a NEW state; invalid input cannot mutate it."""
    view=adventure_view(spec,state)
    if not isinstance(command,str) or len(command)>100: fail('command','expected a short string')
    command=command.strip().lower()
    if command=='restart': return initial_state(spec)
    if command in ('look','help','inventory'): return copy.deepcopy(state)
    choices=view['choices'];chosen=None
    for i,c in enumerate(choices,1):
        if command in [str(i),c['id'].lower(),*[x.strip().lower() for x in c.get('aliases',[])]]: chosen=c;break
    if chosen is None: fail('command','unknown choice; use a listed number or command')
    if not chosen['available']: fail('command','that choice is locked or cannot be paid for')
    st=copy.deepcopy(state);e=chosen.get('effects',{})
    st['inventory']=sorted((set(st['inventory'])-set(e.get('take',[])))|set(e.get('give',[])))
    st['flags']=sorted((set(st['flags'])-set(e.get('clear_flags',[])))|set(e.get('set_flags',[])))
    maxima={x['id']:x['max'] for x in spec.get('resources',[])}
    for k,v in e.get('resources',{}).items(): st['resources'][k]=min(maxima[k],st['resources'][k]+v)
    st['scene']=chosen['to'];st['turn']+=1
    validate(dict(spec,state=st))
    return st

class Canvas:
    """Logical 1200-unit page; exact glyph measurements, explicit overflow errors."""
    def __init__(self,s):
        from paperdaemon.pipeline import charts as CH
        self.CH=CH;self.s=s
        self.width,self.height=CH._page(s,*CH.PAGES[PRESETS[s['type']][0]])
        self.scale=self.width/1200;self.h=self.height/self.scale
        self.p=CH._Px(self.width,self.height);self.layers=[];self.boxes=[]
        self.accent=s.get('accent','teal');self.ink=CH.INK.get(self.accent,CH.GRAY)
        self.rect(0,0,1200,self.h,'white',stroke='white')
        if s['type'] in NO_CHROME:
            # a strip that sits on a page with other things (under a game board): no printable
            # header or footer, just the content and an optional one-line title
            self.top=16;self.bottom=self.h-12
            if s.get('title'):
                self.text(s['title'],44,self.top,18,width=1112,max_lines=1,path='title',color=self.ink)
                self.top+=32
            return
        self.text('TABLETOP  /  '+s['type'].replace('_',' ').upper(),44,30,13,color=self.ink)
        self.text(s['title'],44,58,38,width=1112,max_lines=1,path='title')
        self.top=158
        if s.get('subtitle'): self.text(s['subtitle'],44,116,18,width=1112,max_lines=1,path='subtitle')
        self.line([(44,145),(1156,145)],color=self.ink,width=2)
        self.bottom=self.h-66
        self.line([(44,self.h-51),(1156,self.h-51)],color=CH.RULE,width=.7)
        footer=s.get('footer','DATA-DRIVEN / REMARKABLE TABLETOP')
        self.text(footer,44,self.h-36,12,width=1112,max_lines=1,path='footer',color=CH.GRAY)

    def wash(self,color): return self.CH.WASH[color]
    def add(self,layer): self.layers.append(layer)
    def rect(self,x,y,w,h,color='white',stroke=None,radius=0,width=.9):
        if w<=0 or h<=0: fail('layout','non-positive region; use a larger page')
        s=self.scale
        self.add(self.p.rect([dict(x0=x*s,y0=y*s,x1=(x+w)*s,y1=(y+h)*s,fill=self.wash(color))],
                            stroke=stroke or self.CH.RULE,strokeWidth=width*s,cornerRadius=radius*s))
    def image(self,url,x,y,w,h):
        """A picture (a data URL) in the box whose top-left is (x, y)."""
        s=self.scale
        self.add({'data':{'values':[dict(x=(x+w/2)*s,y=(y+h/2)*s,u=url)]},
                  'mark':dict(type='image',width=w*s,height=h*s,align='center',baseline='middle'),
                  'encoding':self.p.xy(url={'field':'u','type':'nominal'})})
    def line(self,pts,color=None,width=1,dash=None,fill=None):
        mark=dict(color=color or self.CH.RULE,strokeWidth=width*self.scale)
        if dash: mark['strokeDash']=dash
        if fill: mark['fill']=fill
        self.add(self.p.line([dict(x=x*self.scale,y=y*self.scale,k='p',o=i) for i,(x,y) in enumerate(pts)],**mark))
    def circle(self,x,y,r,fill='white',stroke=None):
        self.add({'data':{'values':[dict(x=x*self.scale,y=y*self.scale)]},
                  'mark':dict(type='circle',size=(2*r*self.scale)**2,fill=self.wash(fill),
                              stroke=stroke or self.CH.GRAY,strokeWidth=1.4*self.scale),
                  'encoding':self.p.xy()})
    def icon(self,name,x,y,size,color=None):
        path=self.CH.icon_path(name)
        self.add({'data':{'values':[dict(x=x*self.scale,y=y*self.scale)]},
                  'mark':dict(type='point',shape=path,size=(size*self.scale)**2,filled=False,
                              stroke=color or self.ink,strokeWidth=1.8*self.scale),
                  'encoding':self.p.xy()})
    def measure(self,t,size):
        from paperdaemon.pipeline.draw import glyphs as GL
        return GL.measure(self.CH._in_font(str(t)))*.70*size+size*.15
    def wrap(self,t,size,width,path='text'):
        t=self.CH._in_font(str(t));result=[]
        for para in t.split('\n'):
            line=''
            for word in para.split():
                if self.measure(word,size)>width: fail(path,'unbreakable word is wider than its region')
                trial=(line+' '+word).strip()
                if line and self.measure(trial,size)>width: result.append(line);line=word
                else: line=trial
            result.append(line)
        return result
    def text(self,t,x,y,size=21,width=None,max_lines=None,path='text',color=None,align='left',bold=False):
        lines=self.wrap(t,size,width,path) if width else [self.CH._in_font(str(t))]
        if max_lines is not None and len(lines)>max_lines: fail(path,f'needs {len(lines)} lines; region allows {max_lines}. Shorten text or use more/larger pages')
        height=max(1,len(lines))*size*1.3
        if y+height>self.h-12: fail(path,'text would leave the page')
        vals=[dict(x=x*self.scale,y=(y+i*size*1.3)*self.scale,t=line) for i,line in enumerate(lines)]
        # BOLD IS A STROKE: the tablet's lettering face has one weight, so a heavy line is drawn by
        # outlining its glyphs in their own color
        heavy=dict(stroke=color or self.CH.GRAY,strokeWidth=round(size*self.scale*0.06,2)) if bold else {}
        self.add(self.p.text(vals,size=size*self.scale,bold=bold,color=color or self.CH.GRAY,align=align,baseline='top',**heavy))
        for i,line in enumerate(lines):
            tw=self.measure(line,size);left=x if align=='left' else x-tw/(2 if align=='center' else 1)
            self.boxes.append(dict(text=line,x=left,y=y+i*size*1.3,w=tw,h=size*1.3,path=path))
        return height
    def heading(self,t,x,y,w,color=None):
        self.rect(x,y,w,39,color or 'pale',stroke='white',radius=3)
        self.text(t.upper(),x+12,y+10,17,width=w-24,max_lines=1,path=t)
        return y+52
    def section_height(self,s,w,size=21):
        total=55
        if s.get('text'): total+=len(self.wrap(s['text'],size,w-28,s['title']))*size*1.3+10
        for item in s.get('items',[]): total+=len(self.wrap('- '+item,size,w-28,s['title']))*size*1.3+7
        if s.get('columns'):
            cw=(w-28)/len(s['columns']);rh=0
            for row in [s['columns'],*s.get('rows',[])]:
                rh+=max(len(self.wrap(v,size-2,cw-14,s['title'])) for v in row)*(size-2)*1.3+15
            total+=rh+8
        total+=s.get('lines',0)*34
        return max(100,total+14)
    def section(self,s,x,y,w,limit):
        height=self.section_height(s,w)
        if y+height>limit: fail(s['title'],'section exceeds available height; split content across pages')
        self.rect(x,y,w,height,'white',radius=5)
        q=self.heading(s['title'],x+2,y+2,w-4,s.get('color','pale'))
        if s.get('text'): q+=self.text(s['text'],x+14,q,21,width=w-28,path=s['title'])+10
        for item in s.get('items',[]): q+=self.text('- '+item,x+14,q,21,width=w-28,path=s['title'])+7
        if s.get('columns'):
            cw=(w-28)/len(s['columns'])
            for j,row in enumerate([s['columns'],*s.get('rows',[])]):
                rh=max(len(self.wrap(v,19,cw-14,s['title'])) for v in row)*19*1.3+15
                if j%2==0:self.rect(x+10,q-3,w-20,rh,'pale',stroke='white')
                for k,v in enumerate(row):self.text(v,x+16+k*cw,q+3,19,width=cw-14,path=s['title'])
                q+=rh
        for _ in range(s.get('lines',0)):
            q+=34;self.line([(x+14,q-7),(x+w-14,q-7)],width=.7)
        return y+height+18
    def resources(self,rs,x,y,w):
        if not rs:return y
        gap=14;cw=(w-gap*(len(rs)-1))/len(rs)
        for i,r in enumerate(rs):
            xx=x+i*(cw+gap);self.rect(xx,y,cw,100,'white',radius=5)
            self.text(r['label'].upper(),xx+12,y+10,15,width=cw-24,max_lines=1,path='resources.label')
            self.text(f"{r.get('value',0)} / {r['max']}",xx+12,y+36,25)
            self.rect(xx+12,y+77,cw-24,9,'pale',stroke='white')
            if r.get('value',0): self.rect(xx+12,y+77,(cw-24)*r['value']/r['max'],9,r.get('color',self.accent),stroke='white')
        return y+118
    def spec(self):
        for b in self.boxes:
            if b['x']<0 or b['x']+b['w']>1201: fail(b['path'],'text would leave horizontal page bounds')
        return {'$schema':'https://vega.github.io/schema/vega-lite/v5.json',
                'width':self.width,'height':self.height,'padding':0,'autosize':'none',
                'layer':self.layers,'config':self.CH._config(),
                'usermeta':{'tabletop_version':1,'type':self.s['type'],'text_regions':self.boxes,
                            'logical_size':[1200,self.h]}}

def _board(c,s):
    rows,cols=s['rows'],s['cols'];hexes=s.get('grid','square')=='hex'
    avail=c.bottom-c.top-140
    if hexes:
        rad=min(1080/(math.sqrt(3)*(cols+.5)),avail/(1.5*rows+.5))
        cw=math.sqrt(3)*rad;totalw=cw*(cols+.5);totalh=rad*(1.5*rows+.5)
        x0=(1200-totalw)/2;y0=c.top+24
        pos=lambda r,col:(x0+cw*(col+.5+.5*(r%2)),y0+rad+1.5*rad*r)
        cell_size=cw
    else:
        cell_size=min(1050/cols,avail/rows);totalw=cell_size*cols;totalh=cell_size*rows
        x0=(1200-totalw)/2;y0=c.top+24
        pos=lambda r,col:(x0+(col+.5)*cell_size,y0+(r+.5)*cell_size)
    if cell_size<32: fail('board','cells would be too small; reduce rows/columns or use a taller page')
    overrides={(v['row'],v['col']):v for v in s.get('cells',[])}
    occupied={(v['row'],v['col']) for v in s.get('pieces',[])}
    for r in range(rows):
        for col in range(cols):
            v=overrides.get((r,col),{});x,y=pos(r,col)
            color=v.get('color',s.get('accent','teal') if s.get('checkered',False) and (r+col)%2 else 'white')
            if hexes:
                pts=[(x+rad*math.sin(i*math.pi/3),y-rad*math.cos(i*math.pi/3)) for i in range(7)]
                c.line(pts,width=.8,fill=c.wash(color))
            else:c.rect(x-cell_size/2,y-cell_size/2,cell_size,cell_size,color)
            if (r,col) not in occupied:
                if v.get('icon'):c.icon(v['icon'],x,y-7,cell_size*.22)
                if v.get('label'): c.text(v['label'],x,y+(cell_size*.16 if v.get('icon') else -8),min(17,cell_size*.18),width=cell_size*.82,max_lines=2,align='center',path='cells.label')
                elif hexes and s.get('coordinates',True):c.text(f'{col+1}:{r+1}',x,y+rad*.43,11,align='center')
    if not hexes and s.get('coordinates',True):
        for col in range(cols):c.text(chr(65+col),pos(0,col)[0],y0+totalh+10,16,align='center')
        for r in range(rows):c.text(str(rows-r),x0-17,pos(r,0)[1]-8,16,align='center')
    for p in s.get('pieces',[]):
        x,y=pos(p['row'],p['col']);dark=p.get('side','light')=='dark'
        color=p.get('color','gray' if dark else 'white')
        c.circle(x,y,cell_size*.31,color)
        c.text(p['label'],x,y-cell_size*.12,cell_size*.25,align='center')
    yy=y0+totalh+43
    for note in s.get('notes',[]): yy+=c.text(note,60,yy,18,width=1080,max_lines=2,path='notes')+5
    if yy>c.bottom:fail('notes','board notes exceed the page')

def _mat(c,s):
    y=c.resources(s.get('resources',[]),44,c.top,1112)
    lanes=s['lanes'];n=s.get('slots_per_lane',4);gap=16
    notes_h=70 if s.get('notes') else 0
    lh=(c.bottom-y-notes_h-gap*(len(lanes)-1))/len(lanes)
    if lh<145:fail('lanes','not enough height for writable card slots')
    for i,lane in enumerate(lanes):
        yy=y+i*(lh+gap);color=lane.get('color',c.accent)
        c.rect(44,yy,1112,lh,'white',radius=6);c.rect(44,yy,216,lh,color,radius=6)
        tq=yy+18+c.text(lane['title'],59,yy+18,24,width=184,max_lines=2,path='lanes.title')+16
        c.text(lane.get('action',''),59,tq,16,width=182,max_lines=max(0,int((yy+lh-12-tq)/20.8)),path='lanes.action')
        sw=(876-(n+1)*12)/n
        for j in range(n):
            xx=260+12+j*(sw+12);card=lane.get('slots',[])[j] if j<len(lane.get('slots',[])) else None
            c.rect(xx,yy+12,sw,lh-24,card.get('color','white') if card else 'white',radius=4)
            c.text(str(j+1).zfill(2),xx+10,yy+22,12,color=c.CH.RULE)
            if card:
                if card.get('icon'):c.icon(card['icon'],xx+sw/2,yy+44,20)
                q=yy+70+c.text(card['title'],xx+12,yy+70,18,width=sw-24,max_lines=2,path='slots.title')+7
                c.text(card.get('text',''),xx+12,q,15,width=sw-24,max_lines=max(0,int((yy+lh-22-q)/19.5)),path='slots.text')
    yy=y+len(lanes)*(lh+gap)
    if s.get('notes'): c.text(' / '.join(s['notes']),44,yy,17,width=1112,max_lines=2,path='notes')

def _deck(c,s):
    cols=s.get('columns',2);rows=s.get('rows',3);cap=cols*rows;sheet=s.get('sheet',1)
    cards=s['cards'][(sheet-1)*cap:sheet*cap];gap=22
    w=(1112-gap*(cols-1))/cols;h=(c.bottom-c.top-28-gap*(rows-1))/rows
    if w<220 or h<300: fail('cards','card cells need at least 220 x 300 logical units; reduce columns/rows')
    for i,card in enumerate(cards):
        x=44+i%cols*(w+gap);y=c.top+i//cols*(h+gap);color=card.get('color',c.accent)
        c.rect(x,y,w,h,'white',radius=9);c.rect(x+2,y+2,w-4,38,color,stroke='white',radius=7)
        c.text(card.get('kind','CARD').upper(),x+13,y+13,13,width=w-26,max_lines=1,path='cards.kind')
        if card.get('cost'):c.text(card['cost'],x+w-14,y+52,15,align='right')
        c.text(card['title'],x+18,y+80,28,width=w-36,max_lines=2,path='cards.title')
        q=y+157
        if card.get('subtitle'):q+=c.text(card['subtitle'],x+18,q,17,width=w-36,max_lines=2,path='cards.subtitle')+8
        if card.get('icon'):
            c.icon(card['icon'],x+w/2,q+31,36);q+=78
        bottom=y+h-24
        footer_lines=c.wrap(card.get('footer',''),14,w-36,'cards.footer')
        if card.get('footer'):
            fh=len(footer_lines)*18.2;bottom-=fh+12
            c.text(card['footer'],x+18,bottom+10,14,width=w-36,path='cards.footer')
        if card.get('stats'):
            bottom-=53;sw=(w-36)/len(card['stats'])
            for j,st in enumerate(card['stats']):
                c.text(st['label'].upper(),x+18+j*sw,bottom+4,12,width=sw-8,max_lines=1,path='cards.stats')
                c.text(st.get('value',''),x+18+j*sw,bottom+23,20,width=sw-8,max_lines=1,path='cards.stats')
        c.line([(x+18,q-6),(x+w-18,q-6)],width=.7)
        c.text(card['body'],x+18,q+6,21,width=w-36,max_lines=max(0,int((bottom-q-12)/27.3)),path=f'cards[{i}].body')
        if s.get('cut_guides',True):
            for xx,dx in ((x,-1),(x+w,1)):
                for yy,dy in ((y,-1),(y+h,1)):
                    c.line([(xx+dx*3,yy),(xx+dx*8,yy)],width=.6)
                    c.line([(xx,yy+dy*3),(xx,yy+dy*8)],width=.6)
    c.text(f'SHEET {sheet} / {math.ceil(len(s["cards"])/cap)}',1156,c.bottom-12,12,align='right')

def _character(c,s):
    y=c.top;cw=544
    for i,f in enumerate(s['identity']):
        x=44+(i%2)*568;yy=y+(i//2)*73
        c.text(f['label'].upper(),x,yy,13,color=c.ink)
        c.text(f.get('value',''),x,yy+22,25,width=cw,max_lines=1,path='identity.value')
        c.line([(x,yy+60),(x+cw,yy+60)],width=.8)
    y+=math.ceil(len(s['identity'])/2)*73+14
    stats=s.get('stats',[])
    if stats:
        w=(1112-12*(len(stats)-1))/len(stats)
        for i,f in enumerate(stats):
            x=44+i*(w+12);c.rect(x,y,w,102,'pale',stroke='white',radius=6)
            c.text(f['label'].upper(),x+w/2,y+15,14,width=w-18,max_lines=1,align='center',path='stats.label')
            c.text(f.get('value',''),x+w/2,y+47,31,align='center')
        y+=120
    y=c.resources(s.get('resources',[]),44,y,1112)
    yy=[y,y]
    for section in s['sections']:
        col=0 if yy[0]<=yy[1] else 1
        yy[col]=c.section(section,44+col*568,yy[col],544,c.bottom)
    for col in range(2):
        remaining=c.bottom-yy[col]
        if remaining>=158:
            c.section(dict(title='Additional notes',lines=int((remaining-70)/34)),
                      44+col*568,yy[col],544,c.bottom)

def _screen(c,s):
    n=len(s['panels']);gap=22;w=(1112-gap*(n-1))/n
    for i,p in enumerate(s['panels']):
        x=44+i*(w+gap);y=c.heading(p['title'],x,c.top,w,c.accent)
        for section in p['sections']:y=c.section(section,x,y,w,c.bottom)

def _encounter(c,s):
    y=c.top;c.text('ROUND',44,y+9,16,color=c.ink)
    count=s.get('rounds',10);step=min(70,950/count)
    for i in range(count):
        x=204+i*step;c.circle(x,y+23,min(22,step*.38),c.accent if i+1==s.get('round',1) else 'white')
        c.text(i+1,x,y+12,18,align='center')
    y+=72;y=c.resources(s.get('resources',[]),44,y,1112)
    xs=[44,122,492,620,736];labels=['INIT','ACTOR','HP','DEF','CONDITIONS / NOTES']
    c.rect(44,y,1112,42,c.accent,stroke='white')
    for x,label in zip(xs,labels):c.text(label,x+10,y+12,14)
    y+=42
    rh=min(106,(c.bottom-y-190)/len(s['actors']))
    if rh<62:fail('actors','too many actors for this page; split encounter across pages')
    for i,a in enumerate(s['actors']):
        c.rect(44,y,1112,rh,'white' if i%2 else 'pale',stroke='white')
        vals=[a.get('initiative',''),a['name'],a.get('hp',''),a.get('defense',''),', '.join(a.get('conditions',[]))]
        widths=[70,360,118,106,408]
        last_h=0
        for j,(x,v) in enumerate(zip(xs,vals)):
            hh=c.text(v,x+10,y+14,20,width=widths[j]-18,max_lines=2,path='actors')
            if hh+24>rh:fail('actors','actor text exceeds row height; shorten it or use a taller page')
            if j==4:last_h=hh
        if a.get('notes'):
            ny=y+14+last_h+6
            c.text(a['notes'],746,ny,15,width=394,max_lines=max(0,int((y+rh-8-ny)/19.5)),path='actors.notes')
        c.line([(44,y+rh),(1156,y+rh)],width=.7);y+=rh
    y+=24;c.heading('OBJECTIVES / TERRAIN / CONSEQUENCES',44,y,1112)
    y+=56
    for note in s.get('notes',[]):y+=c.text(note,56,y,20,width=1088,max_lines=2,path='notes')+8
    if y>c.bottom:fail('notes','too many encounter notes')
    if c.bottom-y>180:
        c.section(dict(title='Aftermath / loot / follow-up',lines=int((c.bottom-y-90)/34)),44,y+20,1112,c.bottom)

def _tokens(c,s):
    tokens=[t for t in s['tokens'] for _ in range(t.get('count',1))]
    cols=s.get('columns',5);rows=math.ceil(len(tokens)/cols)
    cw=1112/cols;ch=(c.bottom-c.top)/rows;r=min(cw*.41,ch*.42)
    if r<44:fail('tokens','tokens would be too small; use fewer tokens or a larger page')
    for i,t in enumerate(tokens):
        x=44+(i%cols+.5)*cw;y=c.top+(i//cols+.5)*ch
        if s.get('shape','circle')=='circle':c.circle(x,y,r,t.get('color','white'))
        else:c.rect(x-r,y-r,r*2,r*2,t.get('color','white'),radius=6)
        if t.get('icon'):c.icon(t['icon'],x,y-r*.34,r*.30)
        c.text(t['label'],x,y+(0 if t.get('icon') else -12),min(24,r*.29),width=r*1.7,max_lines=1,align='center',path='tokens.label')
        if t.get('subtitle'):c.text(t['subtitle'],x,y+r*.40,min(14,r*.16),width=r*1.65,max_lines=1,align='center',path='tokens.subtitle')

def _adventure(c,s):
    view=adventure_view(s,s.get('state'));node=view['scene'];st=view['state'];y=c.top
    rs=[dict(r,value=st['resources'][r['id']]) for r in s.get('resources',[])]
    if len(rs)>6:fail('resources','print at most six adventure resources per page')
    y=c.resources(rs,44,y,1112)
    c.text(f"SCENE {node['id'].upper()} / TURN {st['turn']}",44,y+8,14,color=c.ink);y+=46
    c.text(node['title'],44,y,34,width=1030,max_lines=2,path='scene.title');y+=96
    y+=c.text(node['text'],44,y,26,width=1090,max_lines=20,path='scene.text')+34
    if node.get('ending'):
        y=c.heading('THE END / restart to play again',44,y,1112,'green')
    for i,ch in enumerate(view['choices'],1):
        if y+95>c.bottom-125:fail('choices','scene and choices exceed page; shorten narrative or split scene')
        c.rect(44,y,1112,78,c.accent if ch['available'] else 'pale',stroke='white',radius=5)
        c.text(f'{i:02}',62,y+24,23)
        c.text(ch['label'],126,y+13,23,width=997,max_lines=1,path='choices.label')
        c.text('command: '+ch['id']+(' / locked' if not ch['available'] else ''),126,y+47,14,width=997,max_lines=1)
        y+=94
    names={i['id']:i['label'] for i in s.get('items',[])}
    inv=', '.join(names[i] for i in st['inventory']) or 'Empty'
    y+=22;c.text('INVENTORY',44,y,14,color=c.ink);y+=27
    y+=c.text(inv,44,y,21,width=1112,max_lines=3,path='inventory')
    if y>c.bottom:fail('inventory','inventory exceeds available space')

# the narrator speaks in the game board's green: it reads on white (4.7:1), larger than a bubble's words
NARRATOR_INK = '#4F7F3A'


def _dialog(c,s):
    """Speakers as faces with speech bubbles, the narrator as plain words, emotes as a face alone.
    Speakers take sides in the order they first speak (left, right, left...), so a conversation
    reads across the strip; each bubble points at its speaker's face."""
    from paperdaemon.pipeline.games import characters as RC
    tall=c.h>=480
    size=34 if tall else 32;nsize=34 if tall else 32;gap=16 if tall else 12
    # THE NAME UNDER A FACE reads on the tablet: as large as the speech, bold, in ink (at 19 and gray it
    # was too small and too light to make out), with the row under the face grown to hold it
    name_size=size+4;name_row=int(round(name_size*1.3))+8
    order=[]
    for ln in s['lines']:
        if 'speaker' in ln and ln['speaker'] not in order: order.append(ln['speaker'])
    left={cid:i%2==0 for i,cid in enumerate(order)}

    def height(F):
        """The whole dialog's height with faces F units across."""
        total=0
        for i,ln in enumerate(s['lines']):
            if 'narrator' in ln:
                total+=len(c.wrap(ln['narrator'],nsize,1060,f'lines[{i}].narrator'))*nsize*1.3+gap;continue
            row=F+name_row
            if ln.get('text'):
                bw=1200-56-F-42
                row=max(row,len(c.wrap(ln['text'],size,bw-40,f'lines[{i}].text'))*size*1.3+40)
            total+=row+gap
        return total-gap
    # THE LARGEST FACES THAT FIT: a strip under a board holds one speaker at full size, or two at a
    # smaller size; below the floor the faces stop reading, so the page is refused instead
    F=next((f for f in ((180,150,128) if tall else (150,128,110)) if c.top+height(f)<=c.bottom),None)
    if F is None:
        fail('lines','the dialog needs %d units of height and the page has %d; use fewer or shorter lines, or a taller page'
             % (height(110),c.bottom-c.top))
    y=c.top;ink='#2E3136'
    for i,ln in enumerate(s['lines']):
        if 'narrator' in ln:
            lines=c.wrap(ln['narrator'],nsize,1060,f'lines[{i}].narrator');h=len(lines)*nsize*1.3
            if y+h>c.bottom: fail('lines',f'line {i+1} runs past the bottom of the page; use fewer or shorter lines, or a taller page')
            c.rect(56,y+3,6,h-6,'gray',stroke='white')
            c.text(ln['narrator'],78,y,nsize,width=1060,path=f'lines[{i}].narrator',color=NARRATOR_INK)
            y+=h+gap;continue
        p=RC.get(ln['speaker']);on_left=left[p['id']]
        fx=28 if on_left else 1200-28-F
        text=ln.get('text');pad=20
        if text:
            # wrapped at the widest the row allows, then the bubble hugs its longest line
            maxw=1102-F
            tl=c.wrap(text,size,maxw-2*pad,f'lines[{i}].text')
            bw=max(220,min(maxw,max(c.measure(l,size) for l in tl)+2*pad+6))
            bx0=fx+F+42 if on_left else fx-42-bw;bx1=bx0+bw
            bh=max(len(tl)*size*1.3+2*pad,70)
            row=max(F+name_row,bh)
        else:
            row=F+name_row
        if y+row>c.bottom: fail('lines',f'line {i+1} runs past the bottom of the page; use fewer or shorter lines, or a taller page')
        c.image(RC.face_url(p['id'],ln['emotion'],ln.get('marks') or (),front=ln.get('front')),fx,y,F,F)
        c.text(p['short'],fx+F/2,y+F+4,name_size,align='center',color=ink,bold=True)
        if text:
            by=y+max(0,(F-bh)/2)
            c.rect(bx0,by,bw,bh,'white',stroke=ink,radius=20,width=2.2)
            ty=y+F/2
            if on_left: tail=[(bx0+2,ty-15),(bx0-30,ty+4),(bx0+2,ty+13)]
            else: tail=[(bx1-2,ty-15),(bx1+30,ty+4),(bx1-2,ty+13)]
            c.line(tail+[tail[0]],color=ink,width=2.2,fill='#FFFFFF')
            c.line([tail[0],tail[2]],color='#FFFFFF',width=4)      # open the bubble where the tail joins
            c.text(text,bx0+pad,by+pad,size,width=bw-2*pad,path=f'lines[{i}].text',color=ink)
        y+=row+gap

NO_CHROME=('dialog',)
BUILDERS=dict(zip(TYPES,[_board,_mat,_deck,_character,_screen,_encounter,_adventure,_tokens,_dialog]))
def to_vegalite(spec):
    validate(spec);c=Canvas(spec);BUILDERS[spec['type']](c,spec);return c.spec()
