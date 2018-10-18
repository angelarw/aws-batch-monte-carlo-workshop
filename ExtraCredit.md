# Extra credit

Some ideas to expand on this workshop

* In this simple workshop, when we used the Array batch job type to submit jobs, all of the child jobs have the exact same input parameters. Sometimes you may each container to use a different input. For example, if you submit an array job with 50 child job/containers, they each run against a different stock ticker symbol. 

  Update the code and configuration to achieve this. 
  
  > Hint: this [tutorial](https://docs.aws.amazon.com/batch/latest/userguide/array_index_example.html) presents a similar example
  
  
* Use [Amazon Athena](https://aws.amazon.com/athena/) to run SQL queries on top of the result data and use [Amazon QuickSight](https://aws.amazon.com/quicksight/) to visualize it! 
