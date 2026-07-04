var Te=Object.defineProperty;var Ce=Object.getOwnPropertyDescriptor;var h=(r,e,t,i)=>{for(var s=i>1?void 0:i?Ce(e,t):e,n=r.length-1,o;n>=0;n--)(o=r[n])&&(s=(i?o(e,t,s):o(s))||s);return i&&s&&Te(e,t,s),s};var L=globalThis,U=L.ShadowRoot&&(L.ShadyCSS===void 0||L.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Z=Symbol(),oe=new WeakMap,T=class{constructor(e,t,i){if(this._$cssResult$=!0,i!==Z)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(U&&e===void 0){let i=t!==void 0&&t.length===1;i&&(e=oe.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),i&&oe.set(t,e))}return e}toString(){return this.cssText}},ne=r=>new T(typeof r=="string"?r:r+"",void 0,Z),q=(r,...e)=>{let t=r.length===1?r[0]:e.reduce((i,s,n)=>i+(o=>{if(o._$cssResult$===!0)return o.cssText;if(typeof o=="number")return o;throw Error("Value passed to 'css' function must be a 'css' function result: "+o+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+r[n+1],r[0]);return new T(t,r,Z)},ae=(r,e)=>{if(U)r.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let i=document.createElement("style"),s=L.litNonce;s!==void 0&&i.setAttribute("nonce",s),i.textContent=t.cssText,r.appendChild(i)}},V=U?r=>r:r=>r instanceof CSSStyleSheet?(e=>{let t="";for(let i of e.cssRules)t+=i.cssText;return ne(t)})(r):r;var{is:Pe,defineProperty:ze,getOwnPropertyDescriptor:Ie,getOwnPropertyNames:Re,getOwnPropertySymbols:He,getPrototypeOf:Me}=Object,D=globalThis,le=D.trustedTypes,Ne=le?le.emptyScript:"",Oe=D.reactiveElementPolyfillSupport,C=(r,e)=>r,P={toAttribute(r,e){switch(e){case Boolean:r=r?Ne:null;break;case Object:case Array:r=r==null?r:JSON.stringify(r)}return r},fromAttribute(r,e){let t=r;switch(e){case Boolean:t=r!==null;break;case Number:t=r===null?null:Number(r);break;case Object:case Array:try{t=JSON.parse(r)}catch{t=null}}return t}},B=(r,e)=>!Pe(r,e),ce={attribute:!0,type:String,converter:P,reflect:!1,useDefault:!1,hasChanged:B};Symbol.metadata??=Symbol("metadata"),D.litPropertyMetadata??=new WeakMap;var _=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=ce){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let i=Symbol(),s=this.getPropertyDescriptor(e,i,t);s!==void 0&&ze(this.prototype,e,s)}}static getPropertyDescriptor(e,t,i){let{get:s,set:n}=Ie(this.prototype,e)??{get(){return this[t]},set(o){this[t]=o}};return{get:s,set(o){let c=s?.call(this);n?.call(this,o),this.requestUpdate(e,c,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??ce}static _$Ei(){if(this.hasOwnProperty(C("elementProperties")))return;let e=Me(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(C("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(C("properties"))){let t=this.properties,i=[...Re(t),...He(t)];for(let s of i)this.createProperty(s,t[s])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[i,s]of t)this.elementProperties.set(i,s)}this._$Eh=new Map;for(let[t,i]of this.elementProperties){let s=this._$Eu(t,i);s!==void 0&&this._$Eh.set(s,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let i=new Set(e.flat(1/0).reverse());for(let s of i)t.unshift(V(s))}else e!==void 0&&t.push(V(e));return t}static _$Eu(e,t){let i=t.attribute;return i===!1?void 0:typeof i=="string"?i:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let i of t.keys())this.hasOwnProperty(i)&&(e.set(i,this[i]),delete this[i]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return ae(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,i){this._$AK(e,i)}_$ET(e,t){let i=this.constructor.elementProperties.get(e),s=this.constructor._$Eu(e,i);if(s!==void 0&&i.reflect===!0){let n=(i.converter?.toAttribute!==void 0?i.converter:P).toAttribute(t,i.type);this._$Em=e,n==null?this.removeAttribute(s):this.setAttribute(s,n),this._$Em=null}}_$AK(e,t){let i=this.constructor,s=i._$Eh.get(e);if(s!==void 0&&this._$Em!==s){let n=i.getPropertyOptions(s),o=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:P;this._$Em=s;let c=o.fromAttribute(t,n.type);this[s]=c??this._$Ej?.get(s)??c,this._$Em=null}}requestUpdate(e,t,i,s=!1,n){if(e!==void 0){let o=this.constructor;if(s===!1&&(n=this[e]),i??=o.getPropertyOptions(e),!((i.hasChanged??B)(n,t)||i.useDefault&&i.reflect&&n===this._$Ej?.get(e)&&!this.hasAttribute(o._$Eu(e,i))))return;this.C(e,t,i)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:i,reflect:s,wrapped:n},o){i&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,o??t??this[e]),n!==!0||o!==void 0)||(this._$AL.has(e)||(this.hasUpdated||i||(t=void 0),this._$AL.set(e,t)),s===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[s,n]of this._$Ep)this[s]=n;this._$Ep=void 0}let i=this.constructor.elementProperties;if(i.size>0)for(let[s,n]of i){let{wrapped:o}=n,c=this[s];o!==!0||this._$AL.has(s)||c===void 0||this.C(s,void 0,n,c)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(i=>i.hostUpdate?.()),this.update(t)):this._$EM()}catch(i){throw e=!1,this._$EM(),i}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};_.elementStyles=[],_.shadowRootOptions={mode:"open"},_[C("elementProperties")]=new Map,_[C("finalized")]=new Map,Oe?.({ReactiveElement:_}),(D.reactiveElementVersions??=[]).push("2.1.2");var ee=globalThis,de=r=>r,j=ee.trustedTypes,pe=j?j.createPolicy("lit-html",{createHTML:r=>r}):void 0,ye="$lit$",v=`lit$${Math.random().toFixed(9).slice(2)}$`,_e="?"+v,Le=`<${_e}>`,x=document,I=()=>x.createComment(""),R=r=>r===null||typeof r!="object"&&typeof r!="function",te=Array.isArray,Ue=r=>te(r)||typeof r?.[Symbol.iterator]=="function",Y=`[ 	
\f\r]`,z=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,he=/-->/g,ue=/>/g,w=RegExp(`>|${Y}(?:([^\\s"'>=/]+)(${Y}*=${Y}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),me=/'/g,fe=/"/g,be=/^(?:script|style|textarea|title)$/i,ie=r=>(e,...t)=>({_$litType$:r,strings:e,values:t}),l=ie(1),Ge=ie(2),Je=ie(3),S=Symbol.for("lit-noChange"),d=Symbol.for("lit-nothing"),ge=new WeakMap,E=x.createTreeWalker(x,129);function ve(r,e){if(!te(r)||!r.hasOwnProperty("raw"))throw Error("invalid template strings array");return pe!==void 0?pe.createHTML(e):e}var De=(r,e)=>{let t=r.length-1,i=[],s,n=e===2?"<svg>":e===3?"<math>":"",o=z;for(let c=0;c<t;c++){let a=r[c],f,g,m=-1,y=0;for(;y<a.length&&(o.lastIndex=y,g=o.exec(a),g!==null);)y=o.lastIndex,o===z?g[1]==="!--"?o=he:g[1]!==void 0?o=ue:g[2]!==void 0?(be.test(g[2])&&(s=RegExp("</"+g[2],"g")),o=w):g[3]!==void 0&&(o=w):o===w?g[0]===">"?(o=s??z,m=-1):g[1]===void 0?m=-2:(m=o.lastIndex-g[2].length,f=g[1],o=g[3]===void 0?w:g[3]==='"'?fe:me):o===fe||o===me?o=w:o===he||o===ue?o=z:(o=w,s=void 0);let b=o===w&&r[c+1].startsWith("/>")?" ":"";n+=o===z?a+Le:m>=0?(i.push(f),a.slice(0,m)+ye+a.slice(m)+v+b):a+v+(m===-2?c:b)}return[ve(r,n+(r[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),i]},H=class r{constructor({strings:e,_$litType$:t},i){let s;this.parts=[];let n=0,o=0,c=e.length-1,a=this.parts,[f,g]=De(e,t);if(this.el=r.createElement(f,i),E.currentNode=this.el.content,t===2||t===3){let m=this.el.content.firstChild;m.replaceWith(...m.childNodes)}for(;(s=E.nextNode())!==null&&a.length<c;){if(s.nodeType===1){if(s.hasAttributes())for(let m of s.getAttributeNames())if(m.endsWith(ye)){let y=g[o++],b=s.getAttribute(m).split(v),O=/([.?@])?(.*)/.exec(y);a.push({type:1,index:n,name:O[2],strings:b,ctor:O[1]==="."?G:O[1]==="?"?J:O[1]==="@"?Q:k}),s.removeAttribute(m)}else m.startsWith(v)&&(a.push({type:6,index:n}),s.removeAttribute(m));if(be.test(s.tagName)){let m=s.textContent.split(v),y=m.length-1;if(y>0){s.textContent=j?j.emptyScript:"";for(let b=0;b<y;b++)s.append(m[b],I()),E.nextNode(),a.push({type:2,index:++n});s.append(m[y],I())}}}else if(s.nodeType===8)if(s.data===_e)a.push({type:2,index:n});else{let m=-1;for(;(m=s.data.indexOf(v,m+1))!==-1;)a.push({type:7,index:n}),m+=v.length-1}n++}}static createElement(e,t){let i=x.createElement("template");return i.innerHTML=e,i}};function A(r,e,t=r,i){if(e===S)return e;let s=i!==void 0?t._$Co?.[i]:t._$Cl,n=R(e)?void 0:e._$litDirective$;return s?.constructor!==n&&(s?._$AO?.(!1),n===void 0?s=void 0:(s=new n(r),s._$AT(r,t,i)),i!==void 0?(t._$Co??=[])[i]=s:t._$Cl=s),s!==void 0&&(e=A(r,s._$AS(r,e.values),s,i)),e}var W=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:i}=this._$AD,s=(e?.creationScope??x).importNode(t,!0);E.currentNode=s;let n=E.nextNode(),o=0,c=0,a=i[0];for(;a!==void 0;){if(o===a.index){let f;a.type===2?f=new M(n,n.nextSibling,this,e):a.type===1?f=new a.ctor(n,a.name,a.strings,this,e):a.type===6&&(f=new X(n,this,e)),this._$AV.push(f),a=i[++c]}o!==a?.index&&(n=E.nextNode(),o++)}return E.currentNode=x,s}p(e){let t=0;for(let i of this._$AV)i!==void 0&&(i.strings!==void 0?(i._$AI(e,i,t),t+=i.strings.length-2):i._$AI(e[t])),t++}},M=class r{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,i,s){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=i,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=A(this,e,t),R(e)?e===d||e==null||e===""?(this._$AH!==d&&this._$AR(),this._$AH=d):e!==this._$AH&&e!==S&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):Ue(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==d&&R(this._$AH)?this._$AA.nextSibling.data=e:this.T(x.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:i}=e,s=typeof i=="number"?this._$AC(e):(i.el===void 0&&(i.el=H.createElement(ve(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===s)this._$AH.p(t);else{let n=new W(s,this),o=n.u(this.options);n.p(t),this.T(o),this._$AH=n}}_$AC(e){let t=ge.get(e.strings);return t===void 0&&ge.set(e.strings,t=new H(e)),t}k(e){te(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,i,s=0;for(let n of e)s===t.length?t.push(i=new r(this.O(I()),this.O(I()),this,this.options)):i=t[s],i._$AI(n),s++;s<t.length&&(this._$AR(i&&i._$AB.nextSibling,s),t.length=s)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let i=de(e).nextSibling;de(e).remove(),e=i}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},k=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,i,s,n){this.type=1,this._$AH=d,this._$AN=void 0,this.element=e,this.name=t,this._$AM=s,this.options=n,i.length>2||i[0]!==""||i[1]!==""?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=d}_$AI(e,t=this,i,s){let n=this.strings,o=!1;if(n===void 0)e=A(this,e,t,0),o=!R(e)||e!==this._$AH&&e!==S,o&&(this._$AH=e);else{let c=e,a,f;for(e=n[0],a=0;a<n.length-1;a++)f=A(this,c[i+a],t,a),f===S&&(f=this._$AH[a]),o||=!R(f)||f!==this._$AH[a],f===d?e=d:e!==d&&(e+=(f??"")+n[a+1]),this._$AH[a]=f}o&&!s&&this.j(e)}j(e){e===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},G=class extends k{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===d?void 0:e}},J=class extends k{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==d)}},Q=class extends k{constructor(e,t,i,s,n){super(e,t,i,s,n),this.type=5}_$AI(e,t=this){if((e=A(this,e,t,0)??d)===S)return;let i=this._$AH,s=e===d&&i!==d||e.capture!==i.capture||e.once!==i.once||e.passive!==i.passive,n=e!==d&&(i===d||s);s&&this.element.removeEventListener(this.name,this,i),n&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},X=class{constructor(e,t,i){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(e){A(this,e)}};var Be=ee.litHtmlPolyfillSupport;Be?.(H,M),(ee.litHtmlVersions??=[]).push("3.3.3");var $e=(r,e,t)=>{let i=t?.renderBefore??e,s=i._$litPart$;if(s===void 0){let n=t?.renderBefore??null;i._$litPart$=s=new M(e.insertBefore(I(),n),n,void 0,t??{})}return s._$AI(r),s};var se=globalThis,$=class extends _{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=$e(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return S}};$._$litElement$=!0,$.finalized=!0,se.litElementHydrateSupport?.({LitElement:$});var je=se.litElementPolyfillSupport;je?.({LitElement:$});(se.litElementVersions??=[]).push("4.2.2");var we=r=>(e,t)=>{t!==void 0?t.addInitializer(()=>{customElements.define(r,e)}):customElements.define(r,e)};var Ke={attribute:!0,type:String,converter:P,reflect:!1,hasChanged:B},Fe=(r=Ke,e,t)=>{let{kind:i,metadata:s}=t,n=globalThis.litPropertyMetadata.get(s);if(n===void 0&&globalThis.litPropertyMetadata.set(s,n=new Map),i==="setter"&&((r=Object.create(r)).wrapped=!0),n.set(t.name,r),i==="accessor"){let{name:o}=t;return{set(c){let a=e.get.call(this);e.set.call(this,c),this.requestUpdate(o,a,r,!0,c)},init(c){return c!==void 0&&this.C(o,void 0,r,c),c}}}if(i==="setter"){let{name:o}=t;return function(c){let a=this[o];e.call(this,c),this.requestUpdate(o,a,r,!0,c)}}throw Error("Unsupported decorator location: "+i)};function K(r){return(e,t)=>typeof t=="object"?Fe(r,e,t):((i,s,n)=>{let o=s.hasOwnProperty(n);return s.constructor.createProperty(n,i),o?Object.getOwnPropertyDescriptor(s,n):void 0})(r,e,t)}function u(r){return K({...r,state:!0,attribute:!1})}var re=[{code:0,label:"Not used",description:"This zone number has nothing assigned to it.",category:"Special",lifeSafety:!1},{code:1,label:"Entry/Exit (primary)",description:"Your main door. Gives you time to walk out after arming, and time to walk in and disarm before an alarm sounds.",category:"Entry/Exit",lifeSafety:!1},{code:2,label:"Entry/Exit (secondary)",description:"A second, less-used entry door that needs more time to get to the keypad than your main door.",category:"Entry/Exit",lifeSafety:!1},{code:3,label:"Perimeter (instant)",description:"An exterior door or window that should alarm immediately the moment it opens while armed -- no walk-in delay.",category:"Perimeter / Interior",lifeSafety:!1},{code:4,label:"Interior (follower)",description:"An indoor area you pass through after entering (foyer, hallway). Delayed only if a delay door was opened first; otherwise instant. Auto-ignored when armed Stay/Instant.",category:"Perimeter / Interior",lifeSafety:!1},{code:9,label:"Fire (smoke/heat detector)",description:"A hardwired smoke or heat detector. Always active, day or night, armed or not, and cannot be bypassed. Changing a real smoke detector's zone away from this type will silence it.",category:"Life Safety",lifeSafety:!0},{code:16,label:"Fire with verification",description:"Like Fire, but the panel double-checks before sounding, to cut down on false alarms. Always active and cannot be bypassed.",category:"Life Safety",lifeSafety:!0},{code:14,label:"Carbon monoxide detector",description:"A CO detector. Always active and cannot be bypassed.",category:"Life Safety",lifeSafety:!0},{code:6,label:"Panic button (silent)",description:"An emergency button. Notifies the monitoring station only -- no sound at the keypad or siren.",category:"Panic / Emergency",lifeSafety:!1},{code:7,label:"Panic button (audible)",description:"An emergency button. Notifies the monitoring station and sounds the keypad and siren.",category:"Panic / Emergency",lifeSafety:!1},{code:8,label:"Auxiliary alarm (24-hour)",description:"For an emergency button or a monitoring sensor (water, temperature). Notifies the monitoring station and beeps the keypad, but does not sound the siren.",category:"Panic / Emergency",lifeSafety:!1},{code:10,label:"Interior with delay",description:"Like Interior (follower), but always gives the entry delay when armed Away, even if no delay door was tripped first.",category:"Perimeter / Interior",lifeSafety:!1},{code:12,label:"Monitor (trouble only, no alarm)",description:"Reports faults as a non-alarm 'trouble' condition, not a burglary alarm. Do not pair with a relay set to trigger on alarm.",category:"Special",lifeSafety:!1},{code:23,label:"No alarm response",description:"Never triggers an alarm by itself -- useful for an output relay action with no security response.",category:"Special",lifeSafety:!1},{code:24,label:"Silent burglary",description:"Like Perimeter, but with no audible indication anywhere -- only a silent report to the monitoring station.",category:"Perimeter / Interior",lifeSafety:!1}],Ee=Object.fromEntries(re.map(r=>[r.code,r])),xe=[{value:"0",label:"End-of-line resistor (standard, most common)"},{value:"1",label:"Normally closed, no resistor"},{value:"2",label:"Normally open, no resistor"},{value:"3",label:"Zone doubling (two zones share one input)"},{value:"4",label:"Double-balanced (tamper-resistant)"}],Se=[{value:"0",label:"10 ms (fastest, standard wired contacts)"},{value:"1",label:"350 ms"},{value:"2",label:"700 ms"},{value:"3",label:"1.2 seconds (slowest, reduces false trips)"}],N=[{field:"34",label:"Exit delay",description:"How many seconds you have to leave after arming before the exit delay ends. Factory default is 60.",min:0,max:96,specials:{97:"120 seconds"}},{field:"35",label:"Entry delay 1 (primary door)",description:"How many seconds you have to disarm after opening the primary entry door. Factory default is 30.",min:0,max:96,specials:{97:"120 seconds",98:"180 seconds",99:"240 seconds"}},{field:"36",label:"Entry delay 2 (secondary door)",description:"Same as Entry Delay 1, but for secondary entry/exit zones. Factory default is 30.",min:0,max:96,specials:{97:"120 seconds",98:"180 seconds",99:"240 seconds"}},{field:"84",label:"Auto-stay arm",description:"If no delay zone is opened during exit delay, automatically switch the arming mode to Stay. 0=off, 1=partition 1 only, 2=partition 2 only, 3=both. Factory default is 3.",min:0,max:3,specials:{}}],Ae=[{value:0,label:"Default emergency key (fire/police/medical)"},{value:1,label:"Page a number"},{value:2,label:"Show the time"},{value:3,label:"Arm Away"},{value:4,label:"Arm Stay"},{value:5,label:"Arm Night-Stay"},{value:6,label:"Step-arm (Stay, then Night, then Away)"},{value:7,label:"Trigger an output/relay"},{value:8,label:"Send a communication test"}];var ke={disarmed:"Disarmed",armed_away:"Armed \xB7 Away",armed_home:"Armed \xB7 Home",armed_night:"Armed \xB7 Night",arming:"Arming\u2026",pending:"Entry Delay\u2026",triggered:"ALARM",unavailable:"Unavailable",unknown:"Unknown"},p=class extends ${constructor(){super(...arguments);this._showDisarmInput=!1;this._disarmCode="";this._showFieldProgramming=!1;this._progTab="zone";this._progError=null;this._progBusy=!1;this._zpZone="1";this._zpType=3;this._zpPartition="1";this._zpReportEnabled=!0;this._zpHardwireType="0";this._zpResponseTime="1";this._zpConfirm=!1;this._zpConfirmLifeSafety=!1;this._stField=N[0].field;this._stValue="60";this._stConfirm=!1;this._fkKey="A";this._fkPartition="1";this._fkAction=3;this._fkConfirm=!1;this._rawPartition="1";this._rawKeys="";this._rawConfirm=!1}setConfig(t){if(!t.alarm_entity)throw new Error("envisalink-field-programmer-card: `alarm_entity` is required");this._config={show_programming_console:!0,...t}}getCardSize(){return 6}static getStubConfig(){return{alarm_entity:"alarm_control_panel.partition"}}get _entryId(){let t=this.hass?.states[this._config.alarm_entity];return this._config.entry_id??t?.attributes?.config_entry_id}_zoneEntities(){if(!this.hass)return[];if(this._config.zone_entities?.length)return this._config.zone_entities.map(i=>this.hass.states[i]).filter(i=>!!i);let t=this._entryId;return Object.values(this.hass.states).filter(i=>i.entity_id.startsWith("binary_sensor.")&&i.attributes.config_entry_id===t&&i.attributes.zone_number!==void 0)}_troubleEntity(){let t=this._entryId;return Object.values(this.hass.states).find(i=>i.entity_id.startsWith("binary_sensor.")&&i.attributes.config_entry_id===t&&i.attributes.zone_number===void 0)}render(){if(!this.hass||!this._config)return l``;let t=this.hass.states[this._config.alarm_entity];if(!t)return l`<ha-card>
        <div class="warning">Entity ${this._config.alarm_entity} not found.</div>
      </ha-card>`;let i=t.state in ke?t.state:"unknown",s=this._troubleEntity(),n=this._zoneEntities().sort((o,c)=>(o.attributes.zone_number??0)-(c.attributes.zone_number??0));return l`
      <ha-card>
        <div class="console state-${i}">
          <div class="header">
            <div class="title">
              <ha-icon icon="mdi:shield-home"></ha-icon>
              <span>${this._config.title??"Security Console"}</span>
            </div>
            <div class="conn-dot ${t.state==="unavailable"?"off":"on"}"></div>
          </div>

          ${s?.state==="on"?l`<div class="banner trouble">
                <ha-icon icon="mdi:alert"></ha-icon>
                System trouble condition present
              </div>`:d}

          <div class="status-block">
            <div class="status-label">${ke[i]}</div>
            ${this._renderActions(i)}
          </div>

          ${n.length?l`<div class="zones">
                ${n.map(o=>this._renderZone(o))}
              </div>`:d}

          ${this._config.show_programming_console?this._renderFieldProgrammingSection():d}
        </div>
      </ha-card>
    `}_renderActions(t){return t==="disarmed"?l`<div class="actions">
        <button class="btn away" @click=${()=>this._arm("away")}>Away</button>
        <button class="btn home" @click=${()=>this._arm("home")}>Home</button>
        <button class="btn night" @click=${()=>this._arm("night")}>Night</button>
      </div>`:l`<div class="actions">
      ${this._showDisarmInput?l`<input
              class="code-input"
              type="password"
              inputmode="numeric"
              placeholder="Code"
              .value=${this._disarmCode}
              @input=${i=>this._disarmCode=i.target.value}
            />
            <button class="btn disarm" @click=${()=>this._disarm()}>Confirm</button>`:l`<button
            class="btn disarm"
            @click=${()=>this._showDisarmInput=!0}
          >
            Disarm
          </button>`}
    </div>`}_renderZone(t){let i=t.state==="on",s=!!t.attributes.bypassed,n=!!t.attributes.fault,o=!!t.attributes.tamper,c=t.attributes.friendly_name??t.entity_id;return l`<div
      class="zone ${i?"open":"closed"} ${s?"bypassed":""} ${n||o?"fault":""}"
      title=${c}
      @click=${()=>this._toggleBypass(t)}
    >
      <ha-icon icon=${i?"mdi:door-open":"mdi:door-closed"}></ha-icon>
      <span class="zone-name">${c}</span>
      ${s?l`<span class="pill">BYPASS</span>`:d}
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
      </button>`}_renderZoneProgramForm(){let t=Number(this._zpZone)||1,i=Ee[this._zpType],s=t<=8,n=t>=2&&t<=8;return l`
      <div class="prog-row">
        <label>Zone #</label>
        <input
          class="prog-input small"
          type="number"
          min="1"
          max="64"
          .value=${this._zpZone}
          @input=${o=>this._zpZone=o.target.value}
        />
        <label>Partition</label>
        <select
          class="prog-input small"
          .value=${this._zpPartition}
          @change=${o=>this._zpPartition=o.target.value}
        >
          ${[1,2,3].map(o=>l`<option value=${o}>${o}</option>`)}
        </select>
      </div>
      <div class="prog-row column">
        <label>Zone type</label>
        <select
          class="prog-input wide"
          .value=${String(this._zpType)}
          @change=${o=>this._zpType=Number(o.target.value)}
        >
          ${re.map(o=>l`<option value=${o.code}>${o.label}</option>`)}
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
          @change=${o=>this._zpReportEnabled=o.target.checked}
        />
        Report to monitoring station
      </label>
      ${n?l`<div class="prog-row column">
            <label>Hardwire type</label>
            <select
              class="prog-input wide"
              .value=${this._zpHardwireType}
              @change=${o=>this._zpHardwireType=o.target.value}
            >
              ${xe.map(o=>l`<option value=${o.value}>${o.label}</option>`)}
            </select>
          </div>`:d}
      ${s?l`<div class="prog-row column">
            <label>Response time</label>
            <select
              class="prog-input wide"
              .value=${this._zpResponseTime}
              @change=${o=>this._zpResponseTime=o.target.value}
            >
              ${Se.map(o=>l`<option value=${o.value}>${o.label}</option>`)}
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
          @change=${o=>this._zpConfirm=o.target.checked}
        />
        I understand this opens Program Mode on the panel.
      </label>
      ${i?.lifeSafety?l`<label class="confirm-row">
            <input
              type="checkbox"
              .checked=${this._zpConfirmLifeSafety}
              @change=${o=>this._zpConfirmLifeSafety=o.target.checked}
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
          @change=${i=>{this._stField=i.target.value,this._stValue=String(N.find(s=>s.field===this._stField).min)}}
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
              (${Object.entries(t.specials).map(([i,s])=>`${i}=${s}`).join(", ")})
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
          ${Ae.map(t=>l`<option value=${t.value}>${t.label}</option>`)}
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
    `}async _arm(t){await this.hass.callService("alarm_control_panel",`alarm_arm_${t}`,{entity_id:this._config.alarm_entity})}async _disarm(){await this.hass.callService("alarm_control_panel","alarm_disarm",{entity_id:this._config.alarm_entity,code:this._disarmCode||void 0}),this._disarmCode="",this._showDisarmInput=!1}async _toggleBypass(t){let i=this._entryId;if(!i)return;let s=t.attributes.friendly_name??t.entity_id,n=t.attributes.bypassed?"un-bypass":"bypass";window.confirm(`${n==="bypass"?"Bypass":"Un-bypass"} ${s}?`)&&await this.hass.callService("envisalink_field_programmer","toggle_zone_bypass",{entry_id:i,zone:t.attributes.zone_number})}async _sendRawKeystrokes(){let t=this._entryId;if(this._progError=null,!t){this._progError="Could not determine the config entry id for this card.";return}if(!this._rawKeys.trim()){this._progError="Enter a keystroke sequence first.";return}this._progBusy=!0;try{await this.hass.callService("envisalink_field_programmer","send_keystrokes",{entry_id:t,partition:Number(this._rawPartition)||1,keys:this._rawKeys,confirm_installer_risk:this._rawConfirm}),this._rawKeys=""}catch(i){this._progError=i instanceof Error?i.message:String(i)}finally{this._progBusy=!1}}};p.styles=q`
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
    }
    .programming {
      border: 1px solid var(--vc-border);
      border-radius: 12px;
      padding: 12px;
      background: rgba(0, 0, 0, 0.15);
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
  `,h([K({attribute:!1})],p.prototype,"hass",2),h([u()],p.prototype,"_config",2),h([u()],p.prototype,"_showDisarmInput",2),h([u()],p.prototype,"_disarmCode",2),h([u()],p.prototype,"_showFieldProgramming",2),h([u()],p.prototype,"_progTab",2),h([u()],p.prototype,"_progError",2),h([u()],p.prototype,"_progBusy",2),h([u()],p.prototype,"_zpZone",2),h([u()],p.prototype,"_zpType",2),h([u()],p.prototype,"_zpPartition",2),h([u()],p.prototype,"_zpReportEnabled",2),h([u()],p.prototype,"_zpHardwireType",2),h([u()],p.prototype,"_zpResponseTime",2),h([u()],p.prototype,"_zpConfirm",2),h([u()],p.prototype,"_zpConfirmLifeSafety",2),h([u()],p.prototype,"_stField",2),h([u()],p.prototype,"_stValue",2),h([u()],p.prototype,"_stConfirm",2),h([u()],p.prototype,"_fkKey",2),h([u()],p.prototype,"_fkPartition",2),h([u()],p.prototype,"_fkAction",2),h([u()],p.prototype,"_fkConfirm",2),h([u()],p.prototype,"_rawPartition",2),h([u()],p.prototype,"_rawKeys",2),h([u()],p.prototype,"_rawConfirm",2),p=h([we("envisalink-field-programmer-card")],p);window.customCards=window.customCards||[];window.customCards.push({type:"envisalink-field-programmer-card",name:"Envisalink Field Programmer Card",description:"Modern control + guided field-programming console for an alarm panel bridged via Envisalink."});export{p as EnvisalinkFieldProgrammerCard};
