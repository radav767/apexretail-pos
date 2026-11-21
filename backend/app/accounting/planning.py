"""Integer/Fraction accounting plans, never transaction/provider execution."""
from decimal import Decimal,ROUND_HALF_UP
from fractions import Fraction
from fastapi import HTTPException

def amount(value,places):
    if isinstance(value,float) or not isinstance(places,int) or isinstance(places,bool) or not 0<=places<=4:raise HTTPException(422,'Decimal amounts and 0–4 minor-unit places are required')
    try:
        number=Decimal(value);quantum=Decimal(1).scaleb(-places)
        if not number.is_finite() or abs(number)>Decimal('999999999999') or number!=number.quantize(quantum):raise ValueError()
        return int(number/quantum)
    except (ValueError,ArithmeticError):raise HTTPException(422,'Amount exceeds precision or resource bound') from None

def money(units,places):return format(Decimal(units).scaleb(-places),f'.{places}f')
def half_up(value):return (2*value.numerator+value.denominator)//(2*value.denominator)
def apportion(total,weights):
    if not isinstance(total,int) or not 0<=total<=10**16 or not weights or len(weights)>500 or len({str(k) for k,_ in weights})!=len(weights) or any(not isinstance(w,int) or not 0<=w<=10**16 for _,w in weights) or sum(w for _,w in weights)<=0:raise HTTPException(422,'Invalid bounded allocation budget')
    divisor=sum(w for _,w in weights);result={str(k):total*w//divisor for k,w in weights}
    ranked=sorted(weights,key=lambda pair:(-(total*pair[1]%divisor),str(pair[0])))
    for key,_ in ranked[:total-sum(result.values())]:result[str(key)]+=1
    return result

def pricing(lines,places,inclusive,sale_discount=Decimal(0)):
    if not lines or len(lines)>500 or len({str(r['id']) for r in lines})!=len(lines):raise HTTPException(422,'Pricing requires 1–500 distinct lines')
    prepared=[]
    for line in lines:
        qty=Decimal(line['quantity']);factor=Decimal(line.get('factor',1));price=Decimal(line['price']);rate=Decimal(line.get('tax_rate',0))
        if not all(n.is_finite() and n.as_tuple().exponent>=-10 and len(n.as_tuple().digits)<=22 for n in (qty,factor,price,rate)) or not 0<qty<=Decimal('999999999.999') or not 0<factor<=1000000 or not 0<price<=Decimal('999999999999') or not 0<=rate<=100:raise HTTPException(422,'Invalid quantity, configured conversion, price or tax rate')
        base=qty*factor
        if base!=base.quantize(Decimal('.001')):raise HTTPException(422,'Configured conversion exceeds stock precision')
        gross=amount((price*base).quantize(Decimal(1).scaleb(-places),rounding=ROUND_HALF_UP),places);discount=amount(line.get('discount',0),places)
        if discount<0 or gross<=discount:raise HTTPException(422,'Discount must leave a positive line amount')
        prepared.append({'id':str(line['id']),'base_quantity':format(base,'f'),'gross':gross,'line_discount':discount,'weight':gross-discount,'rate':rate})
    discount=amount(sale_discount,places)
    if discount<0 or discount>=sum(r['weight'] for r in prepared):raise HTTPException(422,'Sale discount exceeds eligible positive amount')
    shares=apportion(discount,[(r['id'],r['weight']) for r in prepared]);taxes={}
    for row in prepared:
        row['net']=row['weight']-shares[row['id']]
        if row['net']<=0:raise HTTPException(422,'Allocation leaves a zero-value line')
        taxes[row['id']]=Fraction(row['net'])*Fraction(row['rate'])/(100+Fraction(row['rate']) if inclusive else 100)
    tax=half_up(sum(taxes.values(),Fraction(0)));floors={key:v.numerator//v.denominator for key,v in taxes.items()}
    for key in sorted(taxes,key=lambda k:(-(taxes[k]-floors[k]),k))[:tax-sum(floors.values())]:floors[key]+=1
    net=sum(r['net'] for r in prepared);total=net if inclusive else net+tax
    return {'review_only':True,'posting_enabled':False,'minor_unit_places':places,'gross':money(sum(r['gross'] for r in prepared),places),'discount':money(discount+sum(r['line_discount'] for r in prepared),places),'tax':money(tax,places),'subtotal':money(net-tax if inclusive else net,places),'total':money(total,places),'items':[{'id':r['id'],'base_quantity':r['base_quantity'],'discount':money(r['line_discount']+shares[r['id']],places),'net':money(r['net'],places),'tax':money(floors[r['id']],places)} for r in prepared]}

def tenders(total,base_places,legs):
    target=amount(total,base_places)
    if target<=0 or not 1<=len(legs)<=20 or len({str(r['id']) for r in legs})!=len(legs):raise HTTPException(422,'Tender plan requires 1–20 distinct positive legs')
    values={};original={};change={}
    for leg in legs:
        key=str(leg['id']);places=leg['places'];applied=amount(leg['applied'],places);tendered=amount(leg.get('tendered',leg['applied']),places);rate=Decimal(leg['rate'])
        if leg['method'] not in {'cash','card','mobile','credit'} or applied<=0 or not rate.is_finite() or not 0<rate<=Decimal('10000000000') or rate.as_tuple().exponent < -10 or len(rate.as_tuple().digits)>20:raise HTTPException(422,'Invalid tender method, applied amount or frozen rate')
        if tendered<applied or leg['method']!='cash' and tendered!=applied:raise HTTPException(422,'Only cash can carry original-currency change')
        values[key]=Fraction(applied,10**places)/Fraction(rate)*10**base_places;original[key]=applied;change[key]=tendered-applied
    if half_up(sum(values.values(),Fraction(0)))!=target:raise HTTPException(409,'Tender conversions do not cover the exact sale total')
    allocations={k:v.numerator//v.denominator for k,v in values.items()}
    for key in sorted(values,key=lambda k:(-(values[k]-allocations[k]),k))[:target-sum(allocations.values())]:allocations[key]+=1
    if any(v<=0 for v in allocations.values()):raise HTTPException(422,'Every leg needs a positive base minor-unit allocation')
    for leg in legs:
        if leg.get('quoted_base') is not None and amount(leg['quoted_base'],base_places)!=allocations[str(leg['id'])]:raise HTTPException(409,'Quoted base allocation differs; never alter it silently')
    return {'review_only':True,'posting_enabled':False,'total':money(target,base_places),'credit':money(sum(allocations[str(r['id'])] for r in legs if r['method']=='credit'),base_places),'legs':[{'id':str(r['id']),'method':r['method'],'currency':r['currency'],'applied_original':money(original[str(r['id'])],r['places']),'change_original':money(change[str(r['id'])],r['places']),'applied_base':money(allocations[str(r['id'])],base_places),'provider_confirmed':False} for r in sorted(legs,key=lambda r:str(r['id']))]}

def refunds(total,base_places,legs,unpaid_credit):
    requested=amount(total,base_places);unpaid=amount(unpaid_credit,base_places)
    if requested<=0 or unpaid<0 or not legs or len(legs)>20 or len({str(r['id']) for r in legs})!=len(legs):raise HTTPException(422,'Invalid refund plan')
    remaining=requested;result=[]
    budgets=[]
    for leg in legs:
        applied=amount(leg['applied_base'],base_places);used=amount(leg.get('refunded_base',0),base_places);original=amount(leg['original'],leg['places']);original_used=amount(leg.get('refunded_original',0),leg['places'])
        if not 0<=used<=applied or applied<=0 or not 0<=original_used<=original or original<=0 or leg['method'] not in {'cash','card','mobile','credit'}:raise HTTPException(422,'Refund budget exceeds original allocation')
        if original_used!=half_up(Fraction(original*used,applied)):raise HTTPException(409,'Original-currency cumulative refund proof differs; review original ledger')
        budgets.append((leg,applied,used,original,original_used))
    if unpaid>sum(a-u for leg,a,u,_,_ in budgets if leg['method']=='credit'):raise HTTPException(409,'Unpaid debt exceeds original remaining credit budget')
    for leg,applied,used,original,original_used in sorted(budgets,key=lambda b:(b[0]['method']!='credit',str(b[0]['id']))):
        limit=min(applied-used,unpaid) if leg['method']=='credit' else applied-used
        take=min(remaining,limit)
        if not take:continue
        if leg['method']=='credit':unpaid-=take
        original_take=original-original_used if used+take==applied else half_up(Fraction(original*(used+take),applied))-original_used
        if not 0<=original_take<=original-original_used:raise HTTPException(409,'Original-currency refund residual requires review')
        if leg['method']!='credit' and original_take==0:raise HTTPException(409,'Refund is below original currency minor-unit payout; reviewed allocation is required')
        result.append({'id':str(leg['id']),'kind':'debt_reduction' if leg['method']=='credit' else 'paid_refund','base':money(take,base_places),'original':money(original_take,leg['places'])});remaining-=take
    if remaining:raise HTTPException(409,'Refund exceeds eligible original budgets; collected-credit payout needs reviewed collection allocations')
    return {'review_only':True,'posting_enabled':False,'total':money(requested,base_places),'allocations':result}
