"""Convert native graph cards without changing entities, controls or counter semantics."""
import copy,hashlib,math
CARD='custom:statistics-graph-chart-card'
PALETTE=['#2196f3','#ff9800','#26a69a','#e05a87','#9c6ade','#82b13f','#d9a400','#5f91ad']
def entity_id(e):return e if isinstance(e,str) else e.get('entity','')
def colour(e):return PALETTE[int(hashlib.sha256(e.encode()).hexdigest()[:8],16)%len(PALETTE)]
def numeric(e,meta):
 d=e.split('.')[0];m=meta.get(e,{})
 if d not in ('sensor','input_number','number','counter'):return False
 if m.get('unit') or m.get('numeric') or m.get('state_class'):return True
 return d!='sensor' or not m.get('categorical',False)
def base_card(c,hours):
 o={'type':CARD,'hours_to_show':hours,'height':230,'show_legend':True,
    'show_tooltip_total':False,'animate_graph':False,'update_interval':max(60,c.get('refresh_interval') or 60)}
 if c.get('title'):o['card_header']=c['title']
 for k in ('view_layout','grid_options','visibility','card_mod'):
  if k in c:o[k]=copy.deepcopy(c[k])
 return o
def entry(e,meta,count):
 e={'entity':e} if isinstance(e,str) else copy.deepcopy(e)
 unknown=set(e)-{'entity','name','color','attribute','unit','icon'}
 if unknown:raise ValueError('Unsupported native entity options: '+str(sorted(unknown)))
 e.setdefault('color',colour(e['entity']))
 e.update(show_state=count==1,show_points=False,show_fill=count==1,smooth=False,break_on_null=True)
 return e
def history(c,meta):
 allowed={'type','entities','title','hours_to_show','refresh_interval','logarithmic_scale','min_y_axis','max_y_axis','fit_y_data','view_layout','grid_options','visibility','card_mod'}
 if set(c)-allowed:raise ValueError('Unsupported history graph options: '+str(sorted(set(c)-allowed)))
 hours=c.get('hours_to_show',24);es=c['entities']
 o=base_card(c,hours);o['auto_scale_points']=True;o['points_per_hour']=12
 nums=[e for e in es if numeric(entity_id(e),meta)]
 cats=[e for e in es if not numeric(entity_id(e),meta)]
 if not nums:
  o.update(chart_mode='state_timeline',group_by='raw',data_source='history')
 else:o['chart_mode']='timeline'
 out=[]
 for source in es:
  e=entry(source,meta,len(es));eid=e['entity']
  if not numeric(eid,meta):
   if nums:e['graph_type']='state_strip'
   e['data_source']='history'
   if eid.split('.')[0] in ('binary_sensor','switch','input_boolean','light','fan'):
    e['state_map']=[{'value':'off','color':'#718096'},{'value':'on','color':e['color']}]
  elif meta.get(eid,{}).get('unit') in ('W','kW'):e['points_per_hour']=60
  out.append(e)
 o['entities']=out
 if cats and nums:o['state_strip_titles']=True
 for old,new in [('min_y_axis','lower_bound'),('max_y_axis','upper_bound')]:
  if old in c:o[new]=('~'+str(c[old])) if c.get('fit_y_data') else c[old]
 if c.get('logarithmic_scale'):o['logarithmic']=True
 # Native HA separates different units. Use labelled chart pages rather than
 # plotting unrelated medical or environmental quantities on one numeric axis.
 units={meta.get(entity_id(e),{}).get('unit','') for e in nums}
 if len(units)>1:
  for e in out:
   if numeric(e['entity'],meta):e['graph_group']=meta.get(e['entity'],{}).get('unit') or 'Value'
 return o
def statistics(c,meta):
 allowed={'type','entities','title','days_to_show','chart_type','period','stat_types','hide_legend','logarithmic_scale','min_y_axis','max_y_axis','fit_y_data','expand_legend','energy_date_selection','collection_key','view_layout','grid_options','visibility','card_mod'}
 if set(c)-allowed:raise ValueError('Unsupported statistics options: '+str(sorted(set(c)-allowed)))
 kinds=c.get('stat_types',['mean']);mapping={'mean':'avg','min':'min','max':'max','change':'change'}
 if any(k not in mapping for k in kinds):raise ValueError('Statistics type needs explicit semantics review')
 period=c.get('period','hour');group={'5minute':'interval','hour':'hour','day':'date','week':'week','month':'month','year':'year'}[period]
 o=base_card(c,24*c.get('days_to_show',30));o.update(group_by=group,data_source='statistics',chart_mode='timeline')
 if period=='5minute':o['points_per_hour']=12
 o['show_legend']=not c.get('hide_legend',False)
 if c.get('energy_date_selection'):o['energy_date_selection']=True
 if c.get('collection_key'):raise ValueError('Custom Energy collection requires explicit mapping')
 typ=c.get('chart_type','line')
 if typ not in ('line','bar','line-stack','bar-stack'):raise ValueError('Unsupported statistics chart type')
 if typ.endswith('-stack'):o['stacked']=True
 entities=[]
 for src in c['entities']:
  for kind in kinds:
   e=entry(src,meta,len(c['entities'])*len(kinds));e['aggregate_func']=mapping[kind]
   e['graph_type']='bar' if typ.startswith('bar') else 'line'
   if len(kinds)>1:e['name']=(e.get('name') or meta.get(e['entity'],{}).get('name') or e['entity'])+' · '+kind.title()
   entities.append(e)
 o['entities']=entities
 for old,new in [('min_y_axis','lower_bound'),('max_y_axis','upper_bound')]:
  if old in c:o[new]=('~'+str(c[old])) if c.get('fit_y_data') else c[old]
 return o
def convert(doc,meta):
 count=0
 def visit(x):
  nonlocal count
  if isinstance(x,dict):
   t=x.get('type')
   if t in ('history-graph','statistics-graph'):
    count+=1
    return history(x,meta) if t=='history-graph' else statistics(x,meta)
   return {k:visit(v) for k,v in x.items()}
  if isinstance(x,list):return [visit(v) for v in x]
  return copy.deepcopy(x)
 return visit(doc),count
def graph_count(doc,types=None):
 if types is None:types={'history-graph','statistics-graph',CARD}
 if isinstance(doc,dict):return int(doc.get('type') in types)+sum(graph_count(v,types) for v in doc.values())
 if isinstance(doc,list):return sum(graph_count(v,types) for v in doc)
 return 0
