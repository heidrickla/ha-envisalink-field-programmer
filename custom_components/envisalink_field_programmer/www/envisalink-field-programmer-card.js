var Te=Object.defineProperty;var Ce=Object.getOwnPropertyDescriptor;var h=(n,e,t,i)=>{for(var r=i>1?void 0:i?Ce(e,t):e,o=n.length-1,s;o>=0;o--)(s=n[o])&&(r=(i?s(e,t,r):s(r))||r);return i&&r&&Te(e,t,r),r};var L=globalThis,U=L.ShadowRoot&&(L.ShadyCSS===void 0||L.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Z=Symbol(),ne=new WeakMap,T=class{constructor(e,t,i){if(this._$cssResult$=!0,i!==Z)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(U&&e===void 0){let i=t!==void 0&&t.length===1;i&&(e=ne.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),i&&ne.set(t,e))}return e}toString(){return this.cssText}},oe=n=>new T(typeof n=="string"?n:n+"",void 0,Z),F=(n,...e)=>{let t=n.length===1?n[0]:e.reduce((i,r,o)=>i+(s=>{if(s._$cssResult$===!0)return s.cssText;if(typeof s=="number")return s;throw Error("Value passed to 'css' function must be a 'css' function result: "+s+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+n[o+1],n[0]);return new T(t,n,Z)},ae=(n,e)=>{if(U)n.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let i=document.createElement("style"),r=L.litNonce;r!==void 0&&i.setAttribute("nonce",r),i.textContent=t.cssText,n.appendChild(i)}},V=U?n=>n:n=>n instanceof CSSStyleSheet?(e=>{let t="";for(let i of e.cssRules)t+=i.cssText;return oe(t)})(n):n;var{is:Pe,defineProperty:ze,getOwnPropertyDescriptor:Me,getOwnPropertyNames:Ie,getOwnPropertySymbols:Re,getPrototypeOf:He}=Object,D=globalThis,le=D.trustedTypes,Ne=le?le.emptyScript:"",Oe=D.reactiveElementPolyfillSupport,C=(n,e)=>n,P={toAttribute(n,e){switch(e){case Boolean:n=n?Ne:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,e){let t=n;switch(e){case Boolean:t=n!==null;break;case Number:t=n===null?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch{t=null}}return t}},B=(n,e)=>!Pe(n,e),ce={attribute:!0,type:String,converter:P,reflect:!1,useDefault:!1,hasChanged:B};Symbol.metadata??=Symbol("metadata"),D.litPropertyMetadata??=new WeakMap;var _=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=ce){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let i=Symbol(),r=this.getPropertyDescriptor(e,i,t);r!==void 0&&ze(this.prototype,e,r)}}static getPropertyDescriptor(e,t,i){let{get:r,set:o}=Me(this.prototype,e)??{get(){return this[t]},set(s){this[t]=s}};return{get:r,set(s){let c=r?.call(this);o?.call(this,s),this.requestUpdate(e,c,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??ce}static _$Ei(){if(this.hasOwnProperty(C("elementProperties")))return;let e=He(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(C("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(C("properties"))){let t=this.properties,i=[...Ie(t),...Re(t)];for(let r of i)this.createProperty(r,t[r])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[i,r]of t)this.elementProperties.set(i,r)}this._$Eh=new Map;for(let[t,i]of this.elementProperties){let r=this._$Eu(t,i);r!==void 0&&this._$Eh.set(r,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let i=new Set(e.flat(1/0).reverse());for(let r of i)t.unshift(V(r))}else e!==void 0&&t.push(V(e));return t}static _$Eu(e,t){let i=t.attribute;return i===!1?void 0:typeof i=="string"?i:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let i of t.keys())this.hasOwnProperty(i)&&(e.set(i,this[i]),delete this[i]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return ae(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,i){this._$AK(e,i)}_$ET(e,t){let i=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,i);if(r!==void 0&&i.reflect===!0){let o=(i.converter?.toAttribute!==void 0?i.converter:P).toAttribute(t,i.type);this._$Em=e,o==null?this.removeAttribute(r):this.setAttribute(r,o),this._$Em=null}}_$AK(e,t){let i=this.constructor,r=i._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let o=i.getPropertyOptions(r),s=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:P;this._$Em=r;let c=s.fromAttribute(t,o.type);this[r]=c??this._$Ej?.get(r)??c,this._$Em=null}}requestUpdate(e,t,i,r=!1,o){if(e!==void 0){let s=this.constructor;if(r===!1&&(o=this[e]),i??=s.getPropertyOptions(e),!((i.hasChanged??B)(o,t)||i.useDefault&&i.reflect&&o===this._$Ej?.get(e)&&!this.hasAttribute(s._$Eu(e,i))))return;this.C(e,t,i)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:i,reflect:r,wrapped:o},s){i&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,s??t??this[e]),o!==!0||s!==void 0)||(this._$AL.has(e)||(this.hasUpdated||i||(t=void 0),this._$AL.set(e,t)),r===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[r,o]of this._$Ep)this[r]=o;this._$Ep=void 0}let i=this.constructor.elementProperties;if(i.size>0)for(let[r,o]of i){let{wrapped:s}=o,c=this[r];s!==!0||this._$AL.has(r)||c===void 0||this.C(r,void 0,o,c)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(i=>i.hostUpdate?.()),this.update(t)):this._$EM()}catch(i){throw e=!1,this._$EM(),i}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};_.elementStyles=[],_.shadowRootOptions={mode:"open"},_[C("elementProperties")]=new Map,_[C("finalized")]=new Map,Oe?.({ReactiveElement:_}),(D.reactiveElementVersions??=[]).push("2.1.2");var ee=globalThis,de=n=>n,j=ee.trustedTypes,pe=j?j.createPolicy("lit-html",{createHTML:n=>n}):void 0,ye="$lit$",v=`lit$${Math.random().toFixed(9).slice(2)}$`,_e="?"+v,Le=`<${_e}>`,A=document,M=()=>A.createComment(""),I=n=>n===null||typeof n!="object"&&typeof n!="function",te=Array.isArray,Ue=n=>te(n)||typeof n?.[Symbol.iterator]=="function",Y=`[ 	
\f\r]`,z=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,he=/-->/g,ue=/>/g,w=RegExp(`>|${Y}(?:([^\\s"'>=/]+)(${Y}*=${Y}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),me=/'/g,ge=/"/g,be=/^(?:script|style|textarea|title)$/i,ie=n=>(e,...t)=>({_$litType$:n,strings:e,values:t}),l=ie(1),Ge=ie(2),Je=ie(3),x=Symbol.for("lit-noChange"),d=Symbol.for("lit-nothing"),fe=new WeakMap,E=A.createTreeWalker(A,129);function ve(n,e){if(!te(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return pe!==void 0?pe.createHTML(e):e}var De=(n,e)=>{let t=n.length-1,i=[],r,o=e===2?"<svg>":e===3?"<math>":"",s=z;for(let c=0;c<t;c++){let a=n[c],g,f,m=-1,y=0;for(;y<a.length&&(s.lastIndex=y,f=s.exec(a),f!==null);)y=s.lastIndex,s===z?f[1]==="!--"?s=he:f[1]!==void 0?s=ue:f[2]!==void 0?(be.test(f[2])&&(r=RegExp("</"+f[2],"g")),s=w):f[3]!==void 0&&(s=w):s===w?f[0]===">"?(s=r??z,m=-1):f[1]===void 0?m=-2:(m=s.lastIndex-f[2].length,g=f[1],s=f[3]===void 0?w:f[3]==='"'?ge:me):s===ge||s===me?s=w:s===he||s===ue?s=z:(s=w,r=void 0);let b=s===w&&n[c+1].startsWith("/>")?" ":"";o+=s===z?a+Le:m>=0?(i.push(g),a.slice(0,m)+ye+a.slice(m)+v+b):a+v+(m===-2?c:b)}return[ve(n,o+(n[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),i]},R=class n{constructor({strings:e,_$litType$:t},i){let r;this.parts=[];let o=0,s=0,c=e.length-1,a=this.parts,[g,f]=De(e,t);if(this.el=n.createElement(g,i),E.currentNode=this.el.content,t===2||t===3){let m=this.el.content.firstChild;m.replaceWith(...m.childNodes)}for(;(r=E.nextNode())!==null&&a.length<c;){if(r.nodeType===1){if(r.hasAttributes())for(let m of r.getAttributeNames())if(m.endsWith(ye)){let y=f[s++],b=r.getAttribute(m).split(v),O=/([.?@])?(.*)/.exec(y);a.push({type:1,index:o,name:O[2],strings:b,ctor:O[1]==="."?G:O[1]==="?"?J:O[1]==="@"?Q:k}),r.removeAttribute(m)}else m.startsWith(v)&&(a.push({type:6,index:o}),r.removeAttribute(m));if(be.test(r.tagName)){let m=r.textContent.split(v),y=m.length-1;if(y>0){r.textContent=j?j.emptyScript:"";for(let b=0;b<y;b++)r.append(m[b],M()),E.nextNode(),a.push({type:2,index:++o});r.append(m[y],M())}}}else if(r.nodeType===8)if(r.data===_e)a.push({type:2,index:o});else{let m=-1;for(;(m=r.data.indexOf(v,m+1))!==-1;)a.push({type:7,index:o}),m+=v.length-1}o++}}static createElement(e,t){let i=A.createElement("template");return i.innerHTML=e,i}};function S(n,e,t=n,i){if(e===x)return e;let r=i!==void 0?t._$Co?.[i]:t._$Cl,o=I(e)?void 0:e._$litDirective$;return r?.constructor!==o&&(r?._$AO?.(!1),o===void 0?r=void 0:(r=new o(n),r._$AT(n,t,i)),i!==void 0?(t._$Co??=[])[i]=r:t._$Cl=r),r!==void 0&&(e=S(n,r._$AS(n,e.values),r,i)),e}var W=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:i}=this._$AD,r=(e?.creationScope??A).importNode(t,!0);E.currentNode=r;let o=E.nextNode(),s=0,c=0,a=i[0];for(;a!==void 0;){if(s===a.index){let g;a.type===2?g=new H(o,o.nextSibling,this,e):a.type===1?g=new a.ctor(o,a.name,a.strings,this,e):a.type===6&&(g=new X(o,this,e)),this._$AV.push(g),a=i[++c]}s!==a?.index&&(o=E.nextNode(),s++)}return E.currentNode=A,r}p(e){let t=0;for(let i of this._$AV)i!==void 0&&(i.strings!==void 0?(i._$AI(e,i,t),t+=i.strings.length-2):i._$AI(e[t])),t++}},H=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,i,r){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=i,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=S(this,e,t),I(e)?e===d||e==null||e===""?(this._$AH!==d&&this._$AR(),this._$AH=d):e!==this._$AH&&e!==x&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):Ue(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==d&&I(this._$AH)?this._$AA.nextSibling.data=e:this.T(A.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:i}=e,r=typeof i=="number"?this._$AC(e):(i.el===void 0&&(i.el=R.createElement(ve(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===r)this._$AH.p(t);else{let o=new W(r,this),s=o.u(this.options);o.p(t),this.T(s),this._$AH=o}}_$AC(e){let t=fe.get(e.strings);return t===void 0&&fe.set(e.strings,t=new R(e)),t}k(e){te(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,i,r=0;for(let o of e)r===t.length?t.push(i=new n(this.O(M()),this.O(M()),this,this.options)):i=t[r],i._$AI(o),r++;r<t.length&&(this._$AR(i&&i._$AB.nextSibling,r),t.length=r)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let i=de(e).nextSibling;de(e).remove(),e=i}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},k=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,i,r,o){this.type=1,this._$AH=d,this._$AN=void 0,this.element=e,this.name=t,this._$AM=r,this.options=o,i.length>2||i[0]!==""||i[1]!==""?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=d}_$AI(e,t=this,i,r){let o=this.strings,s=!1;if(o===void 0)e=S(this,e,t,0),s=!I(e)||e!==this._$AH&&e!==x,s&&(this._$AH=e);else{let c=e,a,g;for(e=o[0],a=0;a<o.length-1;a++)g=S(this,c[i+a],t,a),g===x&&(g=this._$AH[a]),s||=!I(g)||g!==this._$AH[a],g===d?e=d:e!==d&&(e+=(g??"")+o[a+1]),this._$AH[a]=g}s&&!r&&this.j(e)}j(e){e===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},G=class extends k{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===d?void 0:e}},J=class extends k{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==d)}},Q=class extends k{constructor(e,t,i,r,o){super(e,t,i,r,o),this.type=5}_$AI(e,t=this){if((e=S(this,e,t,0)??d)===x)return;let i=this._$AH,r=e===d&&i!==d||e.capture!==i.capture||e.once!==i.once||e.passive!==i.passive,o=e!==d&&(i===d||r);r&&this.element.removeEventListener(this.name,this,i),o&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},X=class{constructor(e,t,i){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(e){S(this,e)}};var Be=ee.litHtmlPolyfillSupport;Be?.(R,H),(ee.litHtmlVersions??=[]).push("3.3.3");var $e=(n,e,t)=>{let i=t?.renderBefore??e,r=i._$litPart$;if(r===void 0){let o=t?.renderBefore??null;i._$litPart$=r=new H(e.insertBefore(M(),o),o,void 0,t??{})}return r._$AI(n),r};var re=globalThis,$=class extends _{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=$e(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return x}};$._$litElement$=!0,$.finalized=!0,re.litElementHydrateSupport?.({LitElement:$});var je=re.litElementPolyfillSupport;je?.({LitElement:$});(re.litElementVersions??=[]).push("4.2.2");var we=n=>(e,t)=>{t!==void 0?t.addInitializer(()=>{customElements.define(n,e)}):customElements.define(n,e)};var Ke={attribute:!0,type:String,converter:P,reflect:!1,hasChanged:B},qe=(n=Ke,e,t)=>{let{kind:i,metadata:r}=t,o=globalThis.litPropertyMetadata.get(r);if(o===void 0&&globalThis.litPropertyMetadata.set(r,o=new Map),i==="setter"&&((n=Object.create(n)).wrapped=!0),o.set(t.name,n),i==="accessor"){let{name:s}=t;return{set(c){let a=e.get.call(this);e.set.call(this,c),this.requestUpdate(s,a,n,!0,c)},init(c){return c!==void 0&&this.C(s,void 0,n,c),c}}}if(i==="setter"){let{name:s}=t;return function(c){let a=this[s];e.call(this,c),this.requestUpdate(s,a,n,!0,c)}}throw Error("Unsupported decorator location: "+i)};function K(n){return(e,t)=>typeof t=="object"?qe(n,e,t):((i,r,o)=>{let s=r.hasOwnProperty(o);return r.constructor.createProperty(o,i),s?Object.getOwnPropertyDescriptor(r,o):void 0})(n,e,t)}function u(n){return K({...n,state:!0,attribute:!1})}var se=[{code:0,label:"Not used",description:"This zone number has nothing assigned to it.",category:"Special",lifeSafety:!1},{code:1,label:"Entry/Exit (primary)",description:"Your main door. Gives you time to walk out after arming, and time to walk in and disarm before an alarm sounds.",category:"Entry/Exit",lifeSafety:!1},{code:2,label:"Entry/Exit (secondary)",description:"A second, less-used entry door that needs more time to get to the keypad than your main door.",category:"Entry/Exit",lifeSafety:!1},{code:3,label:"Perimeter (instant)",description:"An exterior door or window that should alarm immediately the moment it opens while armed -- no walk-in delay.",category:"Perimeter / Interior",lifeSafety:!1},{code:4,label:"Interior (follower)",description:"An indoor area you pass through after entering (foyer, hallway). Delayed only if a delay door was opened first; otherwise instant. Auto-ignored when armed Stay/Instant.",category:"Perimeter / Interior",lifeSafety:!1},{code:9,label:"Fire (smoke/heat detector)",description:"A hardwired smoke or heat detector. Always active, day or night, armed or not, and cannot be bypassed. Changing a real smoke detector's zone away from this type will silence it.",category:"Life Safety",lifeSafety:!0},{code:16,label:"Fire with verification",description:"Like Fire, but the panel double-checks before sounding, to cut down on false alarms. Always active and cannot be bypassed.",category:"Life Safety",lifeSafety:!0},{code:14,label:"Carbon monoxide detector",description:"A CO detector. Always active and cannot be bypassed.",category:"Life Safety",lifeSafety:!0},{code:6,label:"Panic button (silent)",description:"An emergency button. Notifies the monitoring station only -- no sound at the keypad or siren.",category:"Panic / Emergency",lifeSafety:!1},{code:7,label:"Panic button (audible)",description:"An emergency button. Notifies the monitoring station and sounds the keypad and siren.",category:"Panic / Emergency",lifeSafety:!1},{code:8,label:"Auxiliary alarm (24-hour)",description:"For an emergency button or a monitoring sensor (water, temperature). Notifies the monitoring station and beeps the keypad, but does not sound the siren.",category:"Panic / Emergency",lifeSafety:!1},{code:10,label:"Interior with delay",description:"Like Interior (follower), but always gives the entry delay when armed Away, even if no delay door was tripped first.",category:"Perimeter / Interior",lifeSafety:!1},{code:12,label:"Monitor (trouble only, no alarm)",description:"Reports faults as a non-alarm 'trouble' condition, not a burglary alarm. Do not pair with a relay set to trigger on alarm.",category:"Special",lifeSafety:!1},{code:23,label:"No alarm response",description:"Never triggers an alarm by itself -- useful for an output relay action with no security response.",category:"Special",lifeSafety:!1},{code:24,label:"Silent burglary",description:"Like Perimeter, but with no audible indication anywhere -- only a silent report to the monitoring station.",category:"Perimeter / Interior",lifeSafety:!1}],Ee=Object.fromEntries(se.map(n=>[n.code,n])),Ae=[{value:"0",label:"End-of-line resistor (standard, most common)"},{value:"1",label:"Normally closed, no resistor"},{value:"2",label:"Normally open, no resistor"},{value:"3",label:"Zone doubling (two zones share one input)"},{value:"4",label:"Double-balanced (tamper-resistant)"}],xe=[{value:"0",label:"10 ms (fastest, standard wired contacts)"},{value:"1",label:"350 ms"},{value:"2",label:"700 ms"},{value:"3",label:"1.2 seconds (slowest, reduces false trips)"}],N=[{field:"34",label:"Exit delay",description:"How many seconds you have to leave after arming before the exit delay ends. Factory default is 60.",min:0,max:96,specials:{97:"120 seconds"}},{field:"35",label:"Entry delay 1 (primary door)",description:"How many seconds you have to disarm after opening the primary entry door. Factory default is 30.",min:0,max:96,specials:{97:"120 seconds",98:"180 seconds",99:"240 seconds"}},{field:"36",label:"Entry delay 2 (secondary door)",description:"Same as Entry Delay 1, but for secondary entry/exit zones. Factory default is 30.",min:0,max:96,specials:{97:"120 seconds",98:"180 seconds",99:"240 seconds"}},{field:"84",label:"Auto-stay arm",description:"If no delay zone is opened during exit delay, automatically switch the arming mode to Stay. 0=off, 1=partition 1 only, 2=partition 2 only, 3=both. Factory default is 3.",min:0,max:3,specials:{}}],Se=[{value:0,label:"Default emergency key (fire/police/medical)"},{value:1,label:"Page a number"},{value:2,label:"Show the time"},{value:3,label:"Arm Away"},{value:4,label:"Arm Stay"},{value:5,label:"Arm Night-Stay"},{value:6,label:"Step-arm (Stay, then Night, then Away)"},{value:7,label:"Trigger an output/relay"},{value:8,label:"Send a communication test"}];var ke={disarmed:"Disarmed",armed_away:"Armed \xB7 Away",armed_home:"Armed \xB7 Home",armed_night:"Armed \xB7 Night",arming:"Arming\u2026",pending:"Entry Delay\u2026",triggered:"ALARM",unavailable:"Unavailable",unknown:"Unknown"},p=class extends ${constructor(){super(...arguments);this._showDisarmInput=!1;this._disarmCode="";this._pendingArmMode=null;this._armCode="";this._actionError=null;this._showFieldProgramming=!1;this._progTab="zone";this._progError=null;this._progBusy=!1;this._zpZone="1";this._zpType=3;this._zpPartition="1";this._zpReportEnabled=!0;this._zpHardwireType="0";this._zpResponseTime="1";this._zpConfirm=!1;this._zpConfirmLifeSafety=!1;this._stField=N[0].field;this._stValue="60";this._stConfirm=!1;this._fkKey="A";this._fkPartition="1";this._fkAction=3;this._fkConfirm=!1;this._rawPartition="1";this._rawKeys="";this._rawConfirm=!1}setConfig(t){if(!t.alarm_entity)throw new Error("envisalink-field-programmer-card: `alarm_entity` is required");this._config={show_programming_console:!0,...t}}getCardSize(){return 6}static getStubConfig(){return{alarm_entity:"alarm_control_panel.partition"}}get _entryId(){let t=this.hass?.states[this._config.alarm_entity];return this._config.entry_id??t?.attributes?.config_entry_id}_zoneEntities(){if(!this.hass)return[];if(this._config.zone_entities?.length)return this._config.zone_entities.map(i=>this.hass.states[i]).filter(i=>!!i);let t=this._entryId;return Object.values(this.hass.states).filter(i=>i.entity_id.startsWith("binary_sensor.")&&i.attributes.config_entry_id===t&&i.attributes.zone_number!==void 0)}_troubleEntity(){let t=this._entryId;return Object.values(this.hass.states).find(i=>i.entity_id.startsWith("binary_sensor.")&&i.attributes.config_entry_id===t&&i.attributes.zone_number===void 0)}render(){if(!this.hass||!this._config)return l``;let t=this.hass.states[this._config.alarm_entity];if(!t)return l`<ha-card>
        <div class="warning">Entity ${this._config.alarm_entity} not found.</div>
      </ha-card>`;let i=t.state in ke?t.state:"unknown",r=this._troubleEntity(),o=this._zoneEntities().sort((s,c)=>(s.attributes.zone_number??0)-(c.attributes.zone_number??0));return l`
      <ha-card>
        <div class="console state-${i}">
          <div class="header">
            <div class="title">
              <ha-icon icon="mdi:shield-home"></ha-icon>
              <span>${this._config.title??"Security Console"}</span>
            </div>
            <div class="conn-dot ${t.state==="unavailable"?"off":"on"}"></div>
          </div>

          ${r?.state==="on"?l`<div class="banner trouble">
                <ha-icon icon="mdi:alert"></ha-icon>
                System trouble condition present
              </div>`:d}

          <div class="status-block">
            <div class="status-label">${ke[i]}</div>
            ${this._renderActions(i,t)}
            ${this._actionError?l`<p class="field-help error">${this._actionError}</p>`:d}
          </div>

          ${this._config.show_programming_console?this._renderFieldProgrammingSection():d}

          ${o.length?l`<div class="zones">
                ${o.map(s=>this._renderZone(s))}
              </div>`:d}
        </div>
      </ha-card>
    `}_renderActions(t,i){if(t==="disarmed"){if(this._pendingArmMode){let s=this._pendingArmMode;return l`<div class="actions">
          <input
            class="code-input"
            type="password"
            inputmode="numeric"
            placeholder="Code"
            .value=${this._armCode}
            @input=${c=>this._armCode=c.target.value}
          />
          <button class="btn ${s}" @click=${()=>this._arm(s)}>
            Confirm
          </button>
          <button
            class="btn disarm"
            @click=${()=>{this._pendingArmMode=null,this._armCode=""}}
          >
            Cancel
          </button>
        </div>`}let r=i.attributes.code_arm_required!==!1,o=s=>r?this._pendingArmMode=s:this._arm(s);return l`<div class="actions">
        <button class="btn away" @click=${()=>o("away")}>Away</button>
        <button class="btn home" @click=${()=>o("home")}>Home</button>
        <button class="btn night" @click=${()=>o("night")}>Night</button>
      </div>`}return l`<div class="actions">
      ${this._showDisarmInput?l`<input
              class="code-input"
              type="password"
              inputmode="numeric"
              placeholder="Code"
              .value=${this._disarmCode}
              @input=${r=>this._disarmCode=r.target.value}
            />
            <button class="btn disarm" @click=${()=>this._disarm()}>Confirm</button>`:l`<button
            class="btn disarm"
            @click=${()=>this._showDisarmInput=!0}
          >
            Disarm
          </button>`}
    </div>`}_renderZone(t){let i=t.state==="on",r=!!t.attributes.bypassed,o=!!t.attributes.fault,s=!!t.attributes.tamper,c=t.attributes.friendly_name??t.entity_id;return l`<div
      class="zone ${i?"open":"closed"} ${r?"bypassed":""} ${o||s?"fault":""}"
      title=${c}
      @click=${()=>this._toggleBypass(t)}
    >
      <ha-icon icon=${i?"mdi:door-open":"mdi:door-closed"}></ha-icon>
      <span class="zone-name">${c}</span>
      ${r?l`<span class="pill">BYPASS</span>`:d}
    </div>`}_renderFieldProgrammingSection(){return this._showFieldProgramming?l`<div class="programming">
      <div class="banner warning">
        <ha-icon icon="mdi:alert-octagon"></ha-icon>
        Every action here opens the panel's installer Program Mode. This
        integration cannot read back what's currently on the keypad display,
        so double-check at the physical keypad first if you're not sure
        what's already programmed -- especially for smoke/CO detector zones.
      </div>
      <div class="tabs">
        ${[{id:"zone",label:"Zones"},{id:"timing",label:"Timing"},{id:"keys",label:"Function Keys"},{id:"raw",label:"Raw"}].map(i=>l`<button
            class="tab ${this._progTab===i.id?"active":""}"
            @click=${()=>{this._progTab=i.id,this._progError=null}}
          >
            ${i.label}
          </button>`)}
      </div>
      ${this._progTab==="zone"?this._renderZoneProgramForm():d}
      ${this._progTab==="timing"?this._renderSystemTimingForm():d}
      ${this._progTab==="keys"?this._renderFunctionKeyForm():d}
      ${this._progTab==="raw"?this._renderRawKeystrokeForm():d}
      ${this._progError?l`<div class="banner trouble">${this._progError}</div>`:d}
      <div class="actions">
        <button
          class="btn disarm"
          @click=${()=>this._showFieldProgramming=!1}
        >
          Close
        </button>
      </div>
    </div>`:l`<button
        class="prog-toggle"
        @click=${()=>this._showFieldProgramming=!0}
      >
        <ha-icon icon="mdi:wrench-cog"></ha-icon>
        Field Programming
      </button>`}_renderZoneProgramForm(){let t=Number(this._zpZone)||1,i=Ee[this._zpType],r=t<=8,o=t>=2&&t<=8;return l`
      <div class="prog-row">
        <label>Zone #</label>
        <input
          class="prog-input small"
          type="number"
          min="1"
          max="64"
          .value=${this._zpZone}
          @input=${s=>this._zpZone=s.target.value}
        />
        <label>Partition</label>
        <select
          class="prog-input small"
          .value=${this._zpPartition}
          @change=${s=>this._zpPartition=s.target.value}
        >
          ${[1,2,3].map(s=>l`<option value=${s}>${s}</option>`)}
        </select>
      </div>
      <div class="prog-row column">
        <label>Zone type</label>
        <select
          class="prog-input wide"
          .value=${String(this._zpType)}
          @change=${s=>this._zpType=Number(s.target.value)}
        >
          ${se.map(s=>l`<option value=${s.code}>${s.label}</option>`)}
        </select>
        ${i?l`<p class="field-help">${i.description}</p>`:d}
      </div>
      ${i?.lifeSafety?l`<div class="banner trouble">
            <ha-icon icon="mdi:fire-alert"></ha-icon>
            This is a life-safety zone type (fire/CO). Getting this wrong on
            a real detector's zone can silence it. Requires an extra
            confirmation below.
          </div>`:d}
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._zpReportEnabled}
          @change=${s=>this._zpReportEnabled=s.target.checked}
        />
        Report to monitoring station
      </label>
      ${o?l`<div class="prog-row column">
            <label>Hardwire type</label>
            <select
              class="prog-input wide"
              .value=${this._zpHardwireType}
              @change=${s=>this._zpHardwireType=s.target.value}
            >
              ${Ae.map(s=>l`<option value=${s.value}>${s.label}</option>`)}
            </select>
          </div>`:d}
      ${r?l`<div class="prog-row column">
            <label>Response time</label>
            <select
              class="prog-input wide"
              .value=${this._zpResponseTime}
              @change=${s=>this._zpResponseTime=s.target.value}
            >
              ${xe.map(s=>l`<option value=${s.value}>${s.label}</option>`)}
            </select>
          </div>`:l`<p class="field-help">
            Zone 9+: treated as an auxiliary-wired zone. Wireless (RF) sensor
            enrollment isn't supported here -- enroll the transmitter at the
            keypad first, then use this to set its type/partition.
          </p>`}
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._zpConfirm}
          @change=${s=>this._zpConfirm=s.target.checked}
        />
        I understand this opens Program Mode on the panel.
      </label>
      ${i?.lifeSafety?l`<label class="confirm-row">
            <input
              type="checkbox"
              .checked=${this._zpConfirmLifeSafety}
              @change=${s=>this._zpConfirmLifeSafety=s.target.checked}
            />
            I confirm this life-safety zone type change is intentional.
          </label>`:d}
      <div class="actions">
        <button class="btn away" ?disabled=${this._progBusy} @click=${()=>this._submitZoneProgram()}>
          Apply
        </button>
      </div>
    `}async _submitZoneProgram(){let t=this._entryId;if(this._progError=null,!t){this._progError="Could not determine the config entry id for this card.";return}if(!this._zpConfirm){this._progError="Check the Program Mode confirmation box first.";return}this._progBusy=!0;try{await this.hass.callService("envisalink_field_programmer","program_zone",{entry_id:t,zone_number:Number(this._zpZone),zone_type:this._zpType,partition:Number(this._zpPartition),report_enabled:this._zpReportEnabled,hardwire_type:this._zpHardwireType,response_time:this._zpResponseTime,confirm:this._zpConfirm,confirm_life_safety:this._zpConfirmLifeSafety})}catch(i){this._progError=i instanceof Error?i.message:String(i)}finally{this._progBusy=!1}}_renderSystemTimingForm(){let t=N.find(i=>i.field===this._stField);return l`
      <div class="prog-row column">
        <label>Field</label>
        <select
          class="prog-input wide"
          .value=${this._stField}
          @change=${i=>{this._stField=i.target.value,this._stValue=String(N.find(r=>r.field===this._stField).min)}}
        >
          ${N.map(i=>l`<option value=${i.field}>${i.label}</option>`)}
        </select>
        <p class="field-help">${t.description}</p>
      </div>
      <div class="prog-row">
        <label>Value</label>
        <input
          class="prog-input small"
          type="number"
          min="0"
          max="240"
          .value=${this._stValue}
          @input=${i=>this._stValue=i.target.value}
        />
        ${Object.keys(t.specials).length?l`<span class="field-help inline">
              (${Object.entries(t.specials).map(([i,r])=>`${i}=${r}`).join(", ")})
            </span>`:d}
      </div>
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._stConfirm}
          @change=${i=>this._stConfirm=i.target.checked}
        />
        I understand this opens Program Mode on the panel.
      </label>
      <div class="actions">
        <button class="btn away" ?disabled=${this._progBusy} @click=${()=>this._submitSystemTiming()}>
          Apply
        </button>
      </div>
    `}async _submitSystemTiming(){let t=this._entryId;if(this._progError=null,!t){this._progError="Could not determine the config entry id for this card.";return}if(!this._stConfirm){this._progError="Check the Program Mode confirmation box first.";return}this._progBusy=!0;try{await this.hass.callService("envisalink_field_programmer","set_system_timing",{entry_id:t,field:this._stField,value:Number(this._stValue),confirm:this._stConfirm})}catch(i){this._progError=i instanceof Error?i.message:String(i)}finally{this._progBusy=!1}}_renderFunctionKeyForm(){return l`
      <div class="prog-row">
        <label>Key</label>
        <select
          class="prog-input small"
          .value=${this._fkKey}
          @change=${t=>this._fkKey=t.target.value}
        >
          ${["A","B","C","D"].map(t=>l`<option value=${t}>${t}</option>`)}
        </select>
        <label>Partition</label>
        <select
          class="prog-input small"
          .value=${this._fkPartition}
          @change=${t=>this._fkPartition=t.target.value}
        >
          ${[1,2,3].map(t=>l`<option value=${t}>${t}</option>`)}
        </select>
      </div>
      <div class="prog-row column">
        <label>Action</label>
        <select
          class="prog-input wide"
          .value=${String(this._fkAction)}
          @change=${t=>this._fkAction=Number(t.target.value)}
        >
          ${Se.map(t=>l`<option value=${t.value}>${t.label}</option>`)}
        </select>
      </div>
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._fkConfirm}
          @change=${t=>this._fkConfirm=t.target.checked}
        />
        I understand this opens Program Mode on the panel.
      </label>
      <div class="actions">
        <button class="btn away" ?disabled=${this._progBusy} @click=${()=>this._submitFunctionKey()}>
          Apply
        </button>
      </div>
    `}async _submitFunctionKey(){let t=this._entryId;if(this._progError=null,!t){this._progError="Could not determine the config entry id for this card.";return}if(!this._fkConfirm){this._progError="Check the Program Mode confirmation box first.";return}this._progBusy=!0;try{await this.hass.callService("envisalink_field_programmer","program_function_key",{entry_id:t,key:this._fkKey,partition:Number(this._fkPartition),action:this._fkAction,confirm:this._fkConfirm})}catch(i){this._progError=i instanceof Error?i.message:String(i)}finally{this._progBusy=!1}}_renderRawKeystrokeForm(){return l`
      <p class="field-help">
        For anything the guided tabs above don't cover. Sequences that open
        Program Mode (installer code followed by 800) need the confirmation
        box below.
      </p>
      <div class="prog-row">
        <label>Partition</label>
        <input
          class="prog-input small"
          type="number"
          min="1"
          max="8"
          .value=${this._rawPartition}
          @input=${t=>this._rawPartition=t.target.value}
        />
      </div>
      <div class="prog-row">
        <label>Keys</label>
        <input
          class="prog-input"
          type="text"
          placeholder="e.g. *101#"
          .value=${this._rawKeys}
          @input=${t=>this._rawKeys=t.target.value}
        />
      </div>
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._rawConfirm}
          @change=${t=>this._rawConfirm=t.target.checked}
        />
        I understand the Program Mode / fire-safety risk above.
      </label>
      <div class="actions">
        <button class="btn away" ?disabled=${this._progBusy} @click=${()=>this._sendRawKeystrokes()}>
          Send
        </button>
      </div>
    `}async _arm(t){this._actionError=null;try{await this.hass.callService("alarm_control_panel",`alarm_arm_${t}`,{entity_id:this._config.alarm_entity,code:this._armCode||void 0}),this._pendingArmMode=null,this._armCode=""}catch(i){this._actionError=this._errorMessage(i,`Failed to arm ${t}.`)}}async _disarm(){this._actionError=null;try{await this.hass.callService("alarm_control_panel","alarm_disarm",{entity_id:this._config.alarm_entity,code:this._disarmCode||void 0}),this._disarmCode="",this._showDisarmInput=!1}catch(t){this._actionError=this._errorMessage(t,"Failed to disarm.")}}_errorMessage(t,i){return t&&typeof t=="object"&&"message"in t&&String(t.message)||i}async _toggleBypass(t){let i=this._entryId;if(!i)return;let r=t.attributes.friendly_name??t.entity_id,o=t.attributes.bypassed?"un-bypass":"bypass";window.confirm(`${o==="bypass"?"Bypass":"Un-bypass"} ${r}?`)&&await this.hass.callService("envisalink_field_programmer","toggle_zone_bypass",{entry_id:i,zone:t.attributes.zone_number})}async _sendRawKeystrokes(){let t=this._entryId;if(this._progError=null,!t){this._progError="Could not determine the config entry id for this card.";return}if(!this._rawKeys.trim()){this._progError="Enter a keystroke sequence first.";return}this._progBusy=!0;try{await this.hass.callService("envisalink_field_programmer","send_keystrokes",{entry_id:t,partition:Number(this._rawPartition)||1,keys:this._rawKeys,confirm_installer_risk:this._rawConfirm}),this._rawKeys=""}catch(i){this._progError=i instanceof Error?i.message:String(i)}finally{this._progBusy=!1}}};p.styles=F`
    :host {
      --vc-bg: #0f172a;
      --vc-bg-raised: #1e293b;
      --vc-border: #334155;
      --vc-text: #e2e8f0;
      --vc-text-dim: #94a3b8;
      /* Accent hues are loosely inspired by the Envisalink/EyezOn bridge
         this card talks to (their site uses a crimson/violet/amber accent
         trio over a dark charcoal base) -- a nod for visual harmony, not a
         reproduction of their branding. Falls back to the light/dark HA
         theme's own tone where it matters (borders, surfaces, text) so this
         only touches the armed-state accent colors, not the whole theme. */
      --vc-away: #e11d48;
      --vc-home: #7c3aed;
      --vc-night: #d97706;
      --vc-safe: #22c55e;
      --vc-danger: #ef4444;
    }
    ha-card {
      overflow: hidden;
      border-radius: 16px;
    }
    .console {
      background: linear-gradient(160deg, var(--vc-bg), var(--vc-bg-raised));
      color: var(--vc-text);
      padding: 16px 18px 20px;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 1.05rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .conn-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .conn-dot.on {
      background: var(--vc-safe);
      box-shadow: 0 0 8px var(--vc-safe);
    }
    .conn-dot.off {
      background: var(--vc-danger);
    }
    .banner {
      display: flex;
      gap: 8px;
      align-items: flex-start;
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 0.85rem;
      margin-bottom: 12px;
      line-height: 1.4;
    }
    .banner.trouble {
      background: rgba(239, 68, 68, 0.15);
      color: #fca5a5;
      border: 1px solid rgba(239, 68, 68, 0.35);
    }
    .banner.warning {
      background: rgba(217, 119, 6, 0.12);
      color: #fcd34d;
      border: 1px solid rgba(217, 119, 6, 0.35);
    }
    .status-block {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--vc-border);
      border-radius: 12px;
      padding: 16px;
      text-align: center;
      margin-bottom: 14px;
    }
    .status-label {
      font-size: 1.4rem;
      font-weight: 700;
      margin-bottom: 12px;
      letter-spacing: 0.01em;
    }
    .state-armed_away .status-label {
      color: var(--vc-away);
    }
    .state-armed_home .status-label {
      color: var(--vc-home);
    }
    .state-armed_night .status-label {
      color: var(--vc-night);
    }
    .state-disarmed .status-label {
      color: var(--vc-safe);
    }
    .state-triggered .status-label {
      color: var(--vc-danger);
      animation: pulse 1s infinite;
    }
    .state-pending .status-label,
    .state-arming .status-label {
      color: var(--vc-night);
      animation: pulse 1.4s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    .actions {
      display: flex;
      gap: 8px;
      justify-content: center;
      flex-wrap: wrap;
    }
    .btn {
      border: none;
      border-radius: 8px;
      padding: 10px 16px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      color: white;
      transition: transform 0.1s ease;
    }
    .btn:active {
      transform: scale(0.96);
    }
    .btn:disabled {
      opacity: 0.5;
      cursor: default;
    }
    .btn.away { background: var(--vc-away); }
    .btn.home { background: var(--vc-home); }
    .btn.night { background: var(--vc-night); color: #1c1917; }
    .btn.disarm { background: var(--vc-safe); color: #0f172a; }
    .code-input, .prog-input {
      background: var(--vc-bg);
      border: 1px solid var(--vc-border);
      color: var(--vc-text);
      border-radius: 8px;
      padding: 9px 10px;
      font-size: 0.9rem;
    }
    .prog-input.small {
      width: 60px;
    }
    .prog-input.wide {
      width: 100%;
    }
    .zones {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }
    .zone {
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--vc-border);
      border-radius: 10px;
      padding: 8px 10px;
      cursor: pointer;
      font-size: 0.82rem;
      transition: border-color 0.15s ease;
    }
    .zone:hover {
      border-color: var(--vc-home);
    }
    .zone.open {
      color: var(--vc-night);
    }
    .zone.closed {
      color: var(--vc-text-dim);
    }
    .zone.fault {
      border-color: var(--vc-danger);
      color: var(--vc-danger);
    }
    .zone-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pill {
      margin-left: auto;
      background: var(--vc-night);
      color: #1c1917;
      font-size: 0.65rem;
      font-weight: 700;
      border-radius: 6px;
      padding: 2px 5px;
    }
    .prog-toggle {
      width: 100%;
      background: transparent;
      border: 1px dashed var(--vc-border);
      color: var(--vc-text-dim);
      border-radius: 10px;
      padding: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      cursor: pointer;
      font-size: 0.85rem;
      margin-bottom: 14px;
    }
    .programming {
      border: 1px solid var(--vc-border);
      border-radius: 12px;
      padding: 12px;
      background: rgba(0, 0, 0, 0.15);
      margin-bottom: 14px;
    }
    .tabs {
      display: flex;
      gap: 4px;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--vc-border);
    }
    .tab {
      background: transparent;
      border: none;
      color: var(--vc-text-dim);
      padding: 8px 10px;
      font-size: 0.82rem;
      cursor: pointer;
      border-bottom: 2px solid transparent;
    }
    .tab.active {
      color: var(--vc-text);
      border-bottom-color: var(--vc-home);
    }
    .prog-row {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .prog-row.column {
      flex-direction: column;
      align-items: stretch;
    }
    .prog-row label {
      min-width: 70px;
      font-size: 0.85rem;
      color: var(--vc-text-dim);
    }
    .field-help {
      font-size: 0.78rem;
      color: var(--vc-text-dim);
      margin: 4px 0 0;
      line-height: 1.4;
    }
    .field-help.inline {
      margin: 0;
      white-space: nowrap;
    }
    .field-help.error {
      color: var(--vc-danger);
    }
    .confirm-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
      color: var(--vc-text-dim);
      margin-bottom: 10px;
    }
    .warning {
      padding: 16px;
      color: var(--vc-danger);
    }
  `,h([K({attribute:!1})],p.prototype,"hass",2),h([u()],p.prototype,"_config",2),h([u()],p.prototype,"_showDisarmInput",2),h([u()],p.prototype,"_disarmCode",2),h([u()],p.prototype,"_pendingArmMode",2),h([u()],p.prototype,"_armCode",2),h([u()],p.prototype,"_actionError",2),h([u()],p.prototype,"_showFieldProgramming",2),h([u()],p.prototype,"_progTab",2),h([u()],p.prototype,"_progError",2),h([u()],p.prototype,"_progBusy",2),h([u()],p.prototype,"_zpZone",2),h([u()],p.prototype,"_zpType",2),h([u()],p.prototype,"_zpPartition",2),h([u()],p.prototype,"_zpReportEnabled",2),h([u()],p.prototype,"_zpHardwireType",2),h([u()],p.prototype,"_zpResponseTime",2),h([u()],p.prototype,"_zpConfirm",2),h([u()],p.prototype,"_zpConfirmLifeSafety",2),h([u()],p.prototype,"_stField",2),h([u()],p.prototype,"_stValue",2),h([u()],p.prototype,"_stConfirm",2),h([u()],p.prototype,"_fkKey",2),h([u()],p.prototype,"_fkPartition",2),h([u()],p.prototype,"_fkAction",2),h([u()],p.prototype,"_fkConfirm",2),h([u()],p.prototype,"_rawPartition",2),h([u()],p.prototype,"_rawKeys",2),h([u()],p.prototype,"_rawConfirm",2),p=h([we("envisalink-field-programmer-card")],p);window.customCards=window.customCards||[];window.customCards.push({type:"envisalink-field-programmer-card",name:"Envisalink Field Programmer Card",description:"Modern control + guided field-programming console for an alarm panel bridged via Envisalink."});export{p as EnvisalinkFieldProgrammerCard};
