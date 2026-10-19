'use strict';
/** A deliberately finite restart budget. Never turns application failures into reboot loops. */
class BackendRecoveryBudget {
 constructor({maxRestarts=2}={}){
  if(!Number.isInteger(maxRestarts)||maxRestarts<0||maxRestarts>3)
   throw new Error('Backend restart limit must be between 0 and 3');
  this.maxRestarts=maxRestarts;
  this.attempts=0;
 }
 nextDelay(){
  if(this.attempts>=this.maxRestarts)return null;
  return 1000*(2**this.attempts++);
 }
}
module.exports={BackendRecoveryBudget};
